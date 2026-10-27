// Adapted from PlasmidCraft (MIT); see licenses/PlasmidCraft-AI-MIT.txt.
//! ChatGPT plan OAuth for a public desktop client. No credentials cross the webview bridge.
//! Contract: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
use crate::ai_vault::{DeviceVault, Vault as LocalVault};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use fs2::FileExt;
use jsonwebtoken::{decode, decode_header, jwk::JwkSet, Algorithm, DecodingKey, Validation};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashMap},
    fs::{self, File, OpenOptions},
    io::Write,
    path::PathBuf,
    sync::Mutex,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use subtle::ConstantTimeEq;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
    sync::{watch, Mutex as AsyncMutex},
};
const ISSUER: &str = "https://auth.openai.com";
const RESOURCE: &str = "https://api.openai.com/v1";
const SCOPES: &str =
    "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct";
fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
fn random(n: usize) -> Result<String, String> {
    let mut bytes = vec![0; n];
    getrandom::fill(&mut bytes).map_err(|_| "Could not generate secure sign-in randomness.")?;
    Ok(URL_SAFE_NO_PAD.encode(bytes))
}
fn host_id() -> Result<String, String> {
    let mut b = [0u8; 16];
    getrandom::fill(&mut b).map_err(|_| "Could not create this host identity.")?;
    b[6] = (b[6] & 15) | 64;
    b[8] = (b[8] & 63) | 128;
    let hex = b.iter().map(|b| format!("{b:02x}")).collect::<String>();
    Ok(format!(
        "urn:uuid:{}-{}-{}-{}-{}",
        &hex[..8],
        &hex[8..12],
        &hex[12..16],
        &hex[16..20],
        &hex[20..]
    ))
}
fn equal(a: &str, b: &str) -> bool {
    a.len() == b.len() && bool::from(a.as_bytes().ct_eq(b.as_bytes()))
}
fn valid_client(s: &str) -> bool {
    s.starts_with("oaiapp_")
        && s.len() <= 256
        && s.bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"_-".contains(&c))
}
fn io_error() -> String {
    "Could not access ChatGPT account settings. Check local file permissions.".into()
}
#[derive(Clone, Serialize, Deserialize)]
struct Registration {
    id: String,
    subject: String,
    email: String,
    generation: u64,
    saved_session: bool,
    plan_enabled: bool,
    #[serde(default)]
    reconsent_required: bool,
}
#[derive(Serialize, Deserialize)]
struct Registry {
    version: u8,
    host_id: String,
    accounts: Vec<Registration>,
    #[serde(default)]
    last_account_id: Option<String>,
    #[serde(default = "default_auto_restore")]
    auto_restore: bool,
}
fn default_auto_restore() -> bool {
    true
}
#[derive(Clone, Serialize, Deserialize)]
pub(crate) struct Credential {
    client_id: String,
    subject: String,
    host_id: String,
    generation: u64,
    access_token: String,
    refresh_token: Option<String>,
    id_token: String,
    scopes: Vec<String>,
    expires_at: u64,
    #[serde(default)]
    earliest_refresh_at: Option<u64>,
}
impl Credential {
    fn enabled(&self) -> bool {
        self.scopes.iter().any(|s| s == "chatgpt.tokens.use.direct")
            && self.scopes.iter().any(|s| s == "resource.invoke")
    }
}
trait Vault: Send + Sync {
    fn read(&self, key: &str) -> Result<Vec<u8>, String>;
    fn write(&self, key: &str, value: &[u8]) -> Result<(), String>;
    fn delete(&self, key: &str) -> Result<(), String>;
}
struct PlatformVault {
    directory: PathBuf,
}
impl PlatformVault {
    fn file(&self, key: &str) -> DeviceVault {
        let name = format!("{:x}.json", Sha256::digest(key.as_bytes()));
        DeviceVault::with_limit(self.directory.join(name), 250000)
    }
}
impl Vault for PlatformVault {
    fn read(&self, key: &str) -> Result<Vec<u8>, String> {
        self.file(key)
            .read_with_legacy(|| legacy_session(key))
            .map_err(|_| "Could not read the saved ChatGPT session on this computer.".to_string())?
            .ok_or("This ChatGPT account needs sign-in again.".into())
    }
    fn write(&self, key: &str, value: &[u8]) -> Result<(), String> {
        self.file(key).write(value).map_err(|_| "Could not save the ChatGPT session on this computer; it is available for this session only.".into())
    }
    fn delete(&self, key: &str) -> Result<(), String> {
        self.file(key).delete().map_err(|_| {
            "The ChatGPT session was disabled, but its saved credentials could not be cleared."
                .into()
        })
    }
}
fn legacy_session(_: &str) -> Option<Vec<u8>> {
    None
}
#[derive(Clone, Deserialize)]
struct Discovery {
    issuer: String,
    authorization_endpoint: String,
    token_endpoint: String,
    jwks_uri: String,
    revocation_endpoint: Option<String>,
}
fn auth_url(value: &str) -> bool {
    reqwest::Url::parse(value).is_ok_and(|u| {
        u.scheme() == "https"
            && u.host_str() == Some("auth.openai.com")
            && u.port().is_none()
            && u.username().is_empty()
            && u.password().is_none()
            && u.query().is_none()
            && u.fragment().is_none()
    })
}
fn validate_discovery(d: &Discovery) -> Result<(), String> {
    if d.issuer != ISSUER
        || d.authorization_endpoint != "https://auth.openai.com/api/accounts/authorize"
        || d.token_endpoint != "https://auth.openai.com/api/accounts/oauth/token"
        || !auth_url(&d.jwks_uri)
        || d.revocation_endpoint.as_ref().is_some_and(|u| !auth_url(u))
    {
        return Err(
            "OpenAI authentication discovery did not match the expected issuer/endpoints.".into(),
        );
    }
    Ok(())
}
fn client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(25))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "Could not initialize ChatGPT transport.".into())
}
async fn body(mut response: reqwest::Response, limit: usize) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| "ChatGPT response was interrupted.")?
    {
        if bytes.len() + chunk.len() > limit {
            return Err("ChatGPT response exceeded the size limit.".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    Ok(bytes)
}
async fn discovery() -> Result<Discovery, String> {
    let response = client()?
        .get(format!("{ISSUER}/.well-known/openid-configuration"))
        .send()
        .await
        .map_err(|_| "Could not reach OpenAI sign-in. Check your connection.")?;
    if !response.status().is_success() {
        return Err("OpenAI sign-in discovery is temporarily unavailable.".into());
    }
    let d: Discovery = serde_json::from_slice(&body(response, 100000).await?)
        .map_err(|_| "Invalid OpenAI discovery document.")?;
    validate_discovery(&d)?;
    Ok(d)
}
#[derive(Deserialize)]
struct Claims {
    sub: String,
    exp: u64,
    iat: u64,
    #[serde(default)]
    nonce: Option<String>,
    #[serde(default)]
    email: Option<String>,
    #[serde(default)]
    azp: Option<String>,
    aud: Value,
}
fn verify_identity(
    token: &str,
    jwks: &JwkSet,
    client_id: &str,
    nonce: Option<&str>,
    expected_subject: Option<&str>,
) -> Result<Claims, String> {
    if token.len() > 64000 {
        return Err("ID token exceeded the size limit.".into());
    }
    let header = decode_header(token).map_err(|_| "Invalid ChatGPT ID token.")?;
    if !matches!(header.alg, Algorithm::RS256 | Algorithm::ES256) {
        return Err("Unsupported ID-token signature algorithm.".into());
    }
    let kid = header
        .kid
        .ok_or("The ID token has no signing-key identifier.")?;
    let key = jwks
        .find(&kid)
        .ok_or("The OpenAI signing key was not found. Try sign-in again.")?;
    if key
        .common
        .key_algorithm
        .as_ref()
        .is_some_and(|a| a.to_string() != format!("{:?}", header.alg))
        || key
            .common
            .public_key_use
            .as_ref()
            .is_some_and(|u| *u != jsonwebtoken::jwk::PublicKeyUse::Signature)
    {
        return Err("The signing key is not authorized for this ID-token algorithm.".into());
    }
    let mut validation = Validation::new(header.alg);
    validation.set_issuer(&[ISSUER]);
    validation.set_audience(&[client_id]);
    validation.leeway = 5;
    validation.validate_nbf = true;
    validation.required_spec_claims.extend([
        "sub".into(),
        "iat".into(),
        "iss".into(),
        "aud".into(),
    ]);
    let claims = decode::<Claims>(
        token,
        &DecodingKey::from_jwk(key).map_err(|_| "Invalid OpenAI signing key.")?,
        &validation,
    )
    .map_err(|_| "ChatGPT identity signature, issuer, audience or expiry could not be verified.")?
    .claims;
    if claims.sub.is_empty()
        || claims.sub.len() > 512
        || claims.iat > now() + 5
        || claims.exp <= now().saturating_sub(5)
        || nonce.is_some_and(|n| !equal(claims.nonce.as_deref().unwrap_or(""), n))
        || expected_subject.is_some_and(|s| s != claims.sub)
        || claims.azp.as_deref().is_some_and(|p| p != client_id)
        || (claims.aud.as_array().is_some_and(|a| a.len() > 1)
            && claims.azp.as_deref() != Some(client_id))
    {
        return Err("ChatGPT identity did not match this sign-in/account.".into());
    }
    Ok(claims)
}
async fn identity(
    d: &Discovery,
    token: &str,
    client_id: &str,
    nonce: Option<&str>,
    subject: Option<&str>,
) -> Result<Claims, String> {
    let response = client()?
        .get(&d.jwks_uri)
        .send()
        .await
        .map_err(|_| "Could not retrieve OpenAI signing keys.")?;
    if !response.status().is_success() {
        return Err("OpenAI signing keys are unavailable. Try again later.".into());
    }
    let jwks: JwkSet = serde_json::from_slice(&body(response, 500000).await?)
        .map_err(|_| "Invalid OpenAI signing-key set.")?;
    verify_identity(token, &jwks, client_id, nonce, subject)
}
#[derive(Deserialize)]
struct TokenResponse {
    #[serde(default)]
    access_token: String,
    #[serde(default)]
    refresh_token: Option<String>,
    #[serde(default)]
    id_token: Option<String>,
    #[serde(default)]
    token_type: String,
    #[serde(default)]
    expires_in: u64,
    #[serde(default)]
    scope: Option<String>,
    #[serde(default)]
    earliest_refresh_at: Option<u64>,
}
fn credential(
    raw: TokenResponse,
    client_id: &str,
    subject: &str,
    host: &str,
    generation: u64,
    old: Option<&Credential>,
) -> Result<Credential, String> {
    let plan_granted = raw
        .scope
        .as_ref()
        .map(|s| {
            s.split_whitespace()
                .any(|s| s == "chatgpt.tokens.use.direct")
        })
        .unwrap_or_else(|| old.is_some_and(Credential::enabled));
    if (plan_granted
        && (!raw.token_type.eq_ignore_ascii_case("bearer")
            || raw.access_token.is_empty()
            || raw.expires_in == 0))
        || raw.access_token.len() > 64000
        || raw.access_token.chars().any(char::is_control)
        || raw.expires_in > 86400
        || raw
            .refresh_token
            .as_ref()
            .is_some_and(|s| s.is_empty() || s.len() > 64000)
        || raw.id_token.as_ref().is_some_and(|s| s.len() > 64000)
    {
        return Err("Invalid ChatGPT token response.".into());
    }
    let scopes = raw
        .scope
        .map(|s| s.split_whitespace().map(str::to_owned).collect())
        .or_else(|| old.map(|o| o.scopes.clone()))
        .ok_or("The sign-in response omitted granted permissions.")?;
    Ok(Credential {
        client_id: client_id.into(),
        subject: subject.into(),
        host_id: host.into(),
        generation,
        access_token: raw.access_token,
        refresh_token: raw
            .refresh_token
            .or_else(|| old.and_then(|c| c.refresh_token.clone())),
        id_token: raw
            .id_token
            .or_else(|| old.map(|c| c.id_token.clone()))
            .ok_or("The sign-in response omitted its ID token.")?,
        scopes,
        expires_at: now() + raw.expires_in,
        earliest_refresh_at: raw.earliest_refresh_at,
    })
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AccountView {
    id: String,
    email: String,
    label: String,
    plan_enabled: bool,
    saved_session: bool,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Status {
    accounts: Vec<AccountView>,
    active_id: Option<String>,
    notice: String,
}
pub struct ChatGptState {
    directory: PathBuf,
    operation: AsyncMutex<()>,
    pending: Mutex<Option<watch::Sender<bool>>>,
    active: Mutex<Option<String>>,
    cache: Mutex<HashMap<String, Credential>>,
    retry_client: Mutex<Option<String>>,
    vault: Box<dyn Vault>,
}
impl ChatGptState {
    pub fn new(directory: PathBuf) -> Self {
        let vault = PlatformVault {
            directory: directory.join("sessions"),
        };
        Self {
            directory,
            operation: AsyncMutex::new(()),
            pending: Mutex::new(None),
            active: Mutex::new(None),
            cache: Mutex::new(HashMap::new()),
            retry_client: Mutex::new(None),
            vault: Box::new(vault),
        }
    }
    fn lock(&self) -> Result<File, String> {
        fs::create_dir_all(&self.directory).map_err(|_| io_error())?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&self.directory, fs::Permissions::from_mode(0o700))
                .map_err(|_| io_error())?;
        }
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(self.directory.join("accounts.lock"))
            .map_err(|_| io_error())?;
        file.try_lock_exclusive().map_err(|_| {
            "Another PyMOL AI-Assistant process is updating this ChatGPT session. Try again shortly."
        })?;
        Ok(file)
    }
    fn registry(&self) -> Result<Registry, String> {
        let path = self.directory.join("accounts.json");
        if !path.exists() {
            let r = Registry {
                version: 1,
                host_id: host_id()?,
                accounts: vec![],
                last_account_id: None,
                auto_restore: true,
            };
            self.save(&r)?;
            return Ok(r);
        }
        if fs::metadata(&path).map_err(|_| io_error())?.len() > 500000 {
            return Err("ChatGPT account settings exceed the size limit.".into());
        }
        let r: Registry = serde_json::from_slice(&fs::read(path).map_err(|_| io_error())?)
            .map_err(|_| "ChatGPT account settings are unreadable; they were not overwritten.")?;
        if r.version != 1
            || !r.host_id.starts_with("urn:uuid:")
            || r.host_id.len() > 128
            || r.accounts.len() > 100
            || r.accounts.iter().any(|a| {
                !valid_client(&a.id)
                    || a.subject.is_empty()
                    || a.subject.len() > 512
                    || a.email.len() > 512
            })
        {
            return Err("Invalid ChatGPT account settings; they were not overwritten.".into());
        }
        Ok(r)
    }
    fn save(&self, r: &Registry) -> Result<(), String> {
        let mut temp = tempfile::NamedTempFile::new_in(&self.directory).map_err(|_| io_error())?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            temp.as_file()
                .set_permissions(fs::Permissions::from_mode(0o600))
                .map_err(|_| io_error())?;
        }
        temp.write_all(&serde_json::to_vec(r).map_err(|_| io_error())?)
            .map_err(|_| io_error())?;
        temp.as_file().sync_all().map_err(|_| io_error())?;
        temp.persist(self.directory.join("accounts.json"))
            .map_err(|_| io_error())?;
        Ok(())
    }
    fn key(r: &Registry, id: &str) -> String {
        format!("{}:{id}", r.host_id)
    }
    fn load(&self, r: &Registry, id: &str) -> Result<Credential, String> {
        let registration = r
            .accounts
            .iter()
            .find(|a| a.id == id)
            .ok_or("Choose a saved ChatGPT account or sign in.")?;
        let c = if registration.saved_session {
            let bytes = self.vault.read(&Self::key(r, id))?;
            if bytes.len() > 250000 {
                return Err("Invalid saved credential size. Sign in again.".into());
            }
            serde_json::from_slice::<Credential>(&bytes)
                .map_err(|_| "Saved ChatGPT credentials are unreadable. Sign in again.")?
        } else {
            self.cache
                .lock()
                .map_err(|_| io_error())?
                .get(id)
                .cloned()
                .ok_or("This account needs sign-in again.")?
        };
        if c.client_id != id
            || c.host_id != r.host_id
            || c.subject != registration.subject
            || c.generation != registration.generation
        {
            return Err(
                "Saved credentials do not match this account registration. Sign in again.".into(),
            );
        }
        Ok(c)
    }
    fn store(&self, r: &mut Registry, c: Credential) -> Result<String, String> {
        let id = c.client_id.clone();
        let key = Self::key(r, &id);
        let bytes = serde_json::to_vec(&c).map_err(|_| io_error())?;
        if bytes.len() > 250000 {
            return Err("ChatGPT credentials exceeded the protected storage limit.".into());
        }
        let warning = self.vault.write(&key, &bytes).err();
        if warning.is_some() {
            let _ = self.vault.delete(&key);
        }
        let a = r
            .accounts
            .iter_mut()
            .find(|a| a.id == id)
            .ok_or("Unknown account registration.")?;
        a.saved_session = warning.is_none();
        a.plan_enabled = c.enabled();
        a.reconsent_required = !c.enabled();
        self.save(r)?;
        self.cache.lock().map_err(|_| io_error())?.insert(id, c);
        Ok(warning.unwrap_or_default())
    }
    fn view(&self, r: Registry, notice: String) -> Result<Status, String> {
        Ok(Status {
            accounts: r
                .accounts
                .into_iter()
                .map(|a| AccountView {
                    label: format!(
                        "{} · {}",
                        if a.email.is_empty() {
                            "ChatGPT account"
                        } else {
                            &a.email
                        },
                        &a.id[a.id.len().saturating_sub(8)..]
                    ),
                    id: a.id,
                    email: a.email,
                    plan_enabled: a.plan_enabled,
                    saved_session: a.saved_session,
                })
                .collect(),
            active_id: self.active.lock().map_err(|_| io_error())?.clone(),
            notice,
        })
    }
    fn activate(&self, r: &mut Registry, id: &str) -> Result<(), String> {
        if !r.accounts.iter().any(|a| a.id == id) {
            return Err("Unknown ChatGPT account.".into());
        }
        r.last_account_id = Some(id.into());
        r.auto_restore = true;
        self.save(r)?;
        *self.active.lock().map_err(|_| io_error())? = Some(id.into());
        Ok(())
    }
    fn clear(&self, r: &mut Registry, id: &str) -> Result<String, String> {
        let key = Self::key(r, id);
        let a = r
            .accounts
            .iter_mut()
            .find(|a| a.id == id)
            .ok_or("Unknown account registration.")?;
        a.generation += 1;
        a.saved_session = false;
        a.plan_enabled = false;
        if r.last_account_id.as_deref() == Some(id) {
            r.last_account_id = None;
            r.auto_restore = false;
        }
        self.save(r)?;
        self.cache.lock().map_err(|_| io_error())?.remove(id);
        let mut active = self.active.lock().map_err(|_| io_error())?;
        if active.as_deref() == Some(id) {
            *active = None;
        }
        Ok(self.vault.delete(&key).err().unwrap_or_default())
    }
}
struct Transaction {
    state: String,
    nonce: String,
    verifier: String,
    redirect: String,
    client_id: Option<String>,
}
impl Transaction {
    fn new(port: u16, client_id: Option<String>) -> Result<Self, String> {
        Ok(Self {
            state: random(32)?,
            nonce: random(32)?,
            verifier: random(64)?,
            redirect: format!("http://127.0.0.1:{port}/auth/callback"),
            client_id,
        })
    }
    fn authorize(&self, d: &Discovery, host: &str) -> Result<String, String> {
        let mut url = reqwest::Url::parse(&d.authorization_endpoint)
            .map_err(|_| "Invalid authorization endpoint.")?;
        {
            let mut q = url.query_pairs_mut();
            q.append_pair(
                "client_id",
                self.client_id.as_deref().unwrap_or("dynamic_agent_client"),
            )
            .append_pair("ext_agent_host_id", host)
            .append_pair("response_type", "code")
            .append_pair("redirect_uri", &self.redirect)
            .append_pair("scope", SCOPES)
            .append_pair("resource", RESOURCE)
            .append_pair("state", &self.state)
            .append_pair("nonce", &self.nonce)
            .append_pair("code_challenge_method", "S256")
            .append_pair(
                "code_challenge",
                &URL_SAFE_NO_PAD.encode(Sha256::digest(self.verifier.as_bytes())),
            );
            if self.client_id.is_none() {
                q.append_pair("agent_name_hint", "PyMOL AI-Assistant");
            }
        }
        Ok(url.into())
    }
}
struct Callback {
    code: String,
    client_id: String,
}
fn callback(target: &str, transaction: &Transaction) -> Result<Callback, String> {
    if !target.starts_with("/auth/callback?") || target.contains('#') || target.len() > 12000 {
        return Err("Invalid sign-in callback path.".into());
    }
    let url = reqwest::Url::parse(&format!("http://127.0.0.1{target}"))
        .map_err(|_| "Invalid callback.")?;
    let mut fields = BTreeMap::new();
    for (k, v) in url.query_pairs() {
        if fields.insert(k.to_string(), v.to_string()).is_some() {
            return Err("Duplicate callback parameter.".into());
        }
    }
    if !equal(
        fields.get("state").map(String::as_str).unwrap_or(""),
        &transaction.state,
    ) {
        return Err("Sign-in state did not match. Start sign-in again.".into());
    }
    if fields.contains_key("error") {
        return Err(
            if fields.get("error").is_some_and(|s| s == "access_denied") {
                "ChatGPT sign-in or plan permission was declined."
            } else {
                "OpenAI could not complete sign-in. Try again."
            }
            .into(),
        );
    }
    let code = fields
        .get("code")
        .filter(|s| !s.is_empty() && s.len() <= 8000)
        .ok_or("Sign-in callback omitted its code.")?
        .clone();
    let issued = fields
        .get("client_id")
        .cloned()
        .or_else(|| transaction.client_id.clone())
        .ok_or("The new registration omitted its issued client ID.")?;
    if !valid_client(&issued)
        || transaction
            .client_id
            .as_ref()
            .is_some_and(|id| id != &issued)
    {
        return Err("The callback client did not match this account registration.".into());
    }
    Ok(Callback {
        code,
        client_id: issued,
    })
}
async fn receive(listener: TcpListener, t: &Transaction) -> Result<Callback, String> {
    loop {
        let (mut stream, _) = listener
            .accept()
            .await
            .map_err(|_| "Could not receive ChatGPT callback.")?;
        let request = tokio::time::timeout(Duration::from_secs(5), async {
            let mut bytes = Vec::new();
            let mut buf = [0; 1024];
            loop {
                let n = stream
                    .read(&mut buf)
                    .await
                    .map_err(|_| "Callback connection was interrupted.")?;
                if n == 0 {
                    return Err("Incomplete callback request.");
                }
                bytes.extend_from_slice(&buf[..n]);
                if bytes.len() > 16000 {
                    return Err("Callback request too large.");
                }
                if bytes.windows(4).any(|s| s == b"\r\n\r\n") {
                    break;
                }
            }
            String::from_utf8(bytes).map_err(|_| "Invalid callback encoding.")
        })
        .await;
        let raw = match request {
            Ok(Ok(r)) => r,
            _ => continue,
        };
        let first = raw.lines().next().unwrap_or("");
        let fields: Vec<_> = first.split_whitespace().collect();
        if fields.len() != 3 || fields[0] != "GET" || !fields[1].starts_with("/auth/callback?") {
            let _ = stream
                .write_all(
                    b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
                )
                .await;
            continue;
        }
        let expected =
            reqwest::Url::parse(&t.redirect).map_err(|_| "Invalid callback listener.")?;
        let host = format!("127.0.0.1:{}", expected.port().unwrap_or(80));
        let returned_host = raw.lines().skip(1).find_map(|l| {
            l.split_once(':')
                .filter(|(k, _)| k.eq_ignore_ascii_case("host"))
                .map(|(_, v)| v.trim())
        });
        let result = if returned_host != Some(host.as_str()) {
            Err("Invalid callback host.".into())
        } else {
            callback(fields[1], t)
        };
        let message = if result.is_ok() {
            "Sign-in returned to PyMOL AI-Assistant. Return to the app to see the result. You can close this tab."
        } else {
            "Sign-in could not be verified. Return to PyMOL AI-Assistant and start again."
        };
        let reply=format!("HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: {}\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nContent-Security-Policy: default-src 'none'; frame-ancestors 'none'\r\nConnection: close\r\n\r\n{}",message.len(),message);
        let _ = stream.write_all(reply.as_bytes()).await;
        return result;
    }
}
fn token_error(status: u16, bytes: &[u8], refresh: bool) -> (String, bool) {
    let data: Value = serde_json::from_slice(bytes).unwrap_or(Value::Null);
    let code = data
        .get("error")
        .and_then(Value::as_str)
        .or_else(|| data.pointer("/error/code").and_then(Value::as_str))
        .unwrap_or("");
    let terminal = refresh
        && matches!(
            code,
            "invalid_grant"
                | "invalid_refresh_token"
                | "token_expired"
                | "refresh_token_expired"
                | "refresh_token_invalidated"
                | "refresh_token_reused"
        );
    let text = if terminal {
        "The ChatGPT session expired or was revoked. Sign in again.".into()
    } else if code == "invalid_grant" {
        "The sign-in code expired or was already used. Start sign-in again.".into()
    } else if code == "invalid_client" {
        "OpenAI rejected this client registration. Reauthorize the selected account or check app eligibility.".into()
    } else {
        format!("OpenAI authorization returned HTTP {status}. Check eligibility/connection and try again. No API-key billing fallback was used.")
    };
    (text, terminal)
}
async fn exchange(
    d: &Discovery,
    form: &[(&str, String)],
    refresh: bool,
) -> Result<TokenResponse, (String, bool)> {
    let response = client()
        .map_err(|s| (s, false))?
        .post(&d.token_endpoint)
        .form(form)
        .send()
        .await
        .map_err(|_| {
            (
                "Could not reach OpenAI token service. Try again later.".into(),
                false,
            )
        })?;
    let status = response.status();
    let bytes = body(response, 250000).await.map_err(|s| (s, false))?;
    if !status.is_success() {
        return Err(token_error(status.as_u16(), &bytes, refresh));
    }
    serde_json::from_slice(&bytes).map_err(|_| ("Invalid OpenAI token response.".into(), false))
}
async fn sign_in_inner(
    state: &ChatGptState,
    selected: Option<String>,
    cancel: &watch::Receiver<bool>,
) -> Result<(String, String), String> {
    let (r, registration) = {
        let _lock = state.lock()?;
        let r = state.registry()?;
        let a = selected
            .as_ref()
            .map(|id| {
                r.accounts
                    .iter()
                    .find(|a| &a.id == id)
                    .cloned()
                    .ok_or("Unknown saved account.")
            })
            .transpose()?;
        (r, a)
    };
    let d = discovery().await?;
    let listener = TcpListener::bind(("127.0.0.1", 0))
        .await
        .map_err(|_| "Could not start local sign-in callback listener.")?;
    let retry = state.retry_client.lock().map_err(|_| io_error())?.clone();
    let t = Transaction::new(
        listener
            .local_addr()
            .map_err(|_| "Could not read callback port.")?
            .port(),
        registration.as_ref().map(|r| r.id.clone()).or(retry),
    )?;
    let mut authorization = reqwest::Url::parse(&t.authorize(&d, &r.host_id)?)
        .map_err(|_| "Invalid authorization URL.")?;
    if registration.as_ref().is_some_and(|a| a.reconsent_required) {
        authorization
            .query_pairs_mut()
            .append_pair("prompt", "consent");
    }
    crate::ai::open_url(authorization.as_str())?;
    let cb = tokio::time::timeout(Duration::from_secs(600), receive(listener, &t))
        .await
        .map_err(|_| "ChatGPT sign-in timed out. Start again.")??;
    let raw = match exchange(
        &d,
        &[
            ("grant_type", "authorization_code".into()),
            ("client_id", cb.client_id.clone()),
            ("code", cb.code),
            ("code_verifier", t.verifier.clone()),
            ("redirect_uri", t.redirect.clone()),
            ("resource", RESOURCE.into()),
        ],
        false,
    )
    .await
    {
        Ok(raw) => raw,
        Err((message, _)) => {
            *state.retry_client.lock().map_err(|_| io_error())? = Some(cb.client_id);
            return Err(message);
        }
    };
    let claims = identity(
        &d,
        raw.id_token
            .as_deref()
            .ok_or("OpenAI did not return an ID token.")?,
        &cb.client_id,
        Some(&t.nonce),
        registration.as_ref().map(|a| a.subject.as_str()),
    )
    .await?;
    if *cancel.borrow() {
        return Err("ChatGPT sign-in canceled.".into());
    }
    let _lock = state.lock()?;
    let mut current = state.registry()?;
    if current.host_id != r.host_id {
        return Err("The host registration changed. Start sign-in again.".into());
    }
    if let Some(original) = &registration {
        if current
            .accounts
            .iter()
            .find(|a| a.id == original.id)
            .map(|a| a.generation)
            != Some(original.generation)
        {
            return Err("This account changed in another app process. Start sign-in again.".into());
        }
    }
    let generation = if let Some(a) = current.accounts.iter_mut().find(|a| a.id == cb.client_id) {
        if a.subject != claims.sub {
            return Err("The account identity did not match its registered client.".into());
        }
        a.generation += 1;
        a.generation
    } else {
        if current.accounts.len() >= 100 {
            return Err("Account-registration limit reached.".into());
        }
        current.accounts.push(Registration {
            id: cb.client_id.clone(),
            subject: claims.sub.clone(),
            email: claims
                .email
                .clone()
                .unwrap_or_default()
                .chars()
                .take(512)
                .collect(),
            generation: 1,
            saved_session: false,
            plan_enabled: false,
            reconsent_required: false,
        });
        1
    };
    let c = credential(
        raw,
        &cb.client_id,
        &claims.sub,
        &current.host_id,
        generation,
        None,
    )?;
    let enabled = c.enabled();
    state.save(&current)?;
    let warning = state.store(&mut current, c)?;
    *state.retry_client.lock().map_err(|_| io_error())? = None;
    state.activate(&mut current, &cb.client_id)?;
    let notice = if !enabled {
        "Identity verified, but ChatGPT plan use was not granted. Reauthorize this account and approve plan access before sending requests.".into()
    } else {
        warning
    };
    Ok((cb.client_id, notice))
}
pub fn chatgpt_status(state: &ChatGptState) -> Result<Status, String> {
    let _lock = state.lock()?;
    let r = state.registry()?;
    state.view(r, String::new())
}
pub fn chatgpt_cancel(state: &ChatGptState) -> Result<(), String> {
    if let Some(cancel) = state.pending.lock().map_err(|_| io_error())?.as_ref() {
        let _ = cancel.send(true);
    }
    Ok(())
}
pub async fn chatgpt_sign_in(
    registration_id: Option<String>,
    state: &ChatGptState,
    ai: &crate::ai::AiState,
) -> Result<Status, String> {
    let _op = state
        .operation
        .try_lock()
        .map_err(|_| "Another ChatGPT operation is running.")?;
    let (tx, mut cancel) = watch::channel(false);
    *state.pending.lock().map_err(|_| io_error())? = Some(tx);
    let observed = cancel.clone();
    let result = tokio::select! {value=sign_in_inner(&state,registration_id,&observed)=>value,_=cancel.changed()=>Err("ChatGPT sign-in canceled.".into())};
    *state.pending.lock().map_err(|_| io_error())? = None;
    let (id, notice) = result?;
    if *cancel.borrow() {
        return Err("ChatGPT sign-in canceled.".into());
    }
    crate::ai::connect_chatgpt(&ai, &id)?;
    let _lock = state.lock()?;
    let r = state.registry()?;
    state.view(r, notice)
}
async fn fresh(state: &ChatGptState, r: &mut Registry, id: &str) -> Result<Credential, String> {
    let old = state.load(r, id)?;
    if !old.enabled() || old.expires_at > now() + 60 {
        return Ok(old);
    }
    if old
        .earliest_refresh_at
        .is_some_and(|earliest| earliest > now())
    {
        return Err("ChatGPT requested a later token renewal. Try again shortly.".into());
    }
    let refresh = old
        .refresh_token
        .clone()
        .ok_or("This ChatGPT session cannot renew. Sign in again.")?;
    let d = discovery().await?;
    renew_with_discovery(state, r, id, old, refresh, &d).await
}
async fn renew_with_discovery(
    state: &ChatGptState,
    r: &mut Registry,
    id: &str,
    old: Credential,
    refresh: String,
    d: &Discovery,
) -> Result<Credential, String> {
    let raw = match exchange(
        &d,
        &[
            ("grant_type", "refresh_token".into()),
            ("client_id", id.into()),
            ("refresh_token", refresh),
            ("resource", RESOURCE.into()),
        ],
        true,
    )
    .await
    {
        Ok(raw) => raw,
        Err((message, terminal)) => {
            if terminal {
                let _ = state.clear(r, id)?;
            }
            return Err(message);
        }
    };
    if let Some(token) = &raw.id_token {
        identity(&d, token, id, None, Some(&old.subject)).await?;
    }
    let c = credential(
        raw,
        id,
        &old.subject,
        &r.host_id,
        old.generation,
        Some(&old),
    )?;
    let notice = state.store(r, c.clone())?;
    if !notice.is_empty() {
        return Err(notice);
    }
    Ok(c)
}
pub async fn chatgpt_activate(
    registration_id: String,
    state: &ChatGptState,
    ai: &crate::ai::AiState,
) -> Result<Status, String> {
    let _op = state
        .operation
        .try_lock()
        .map_err(|_| "Another ChatGPT operation is running.")?;
    let _lock = state.lock()?;
    let mut r = state.registry()?;
    let c = fresh(&state, &mut r, &registration_id).await?;
    state.activate(&mut r, &registration_id)?;
    crate::ai::connect_chatgpt(&ai, &registration_id)?;
    state.view(
        r,
        if c.enabled() {
            String::new()
        } else {
            "This account has not granted ChatGPT plan usage. Reauthorize it first.".into()
        },
    )
}
// Restoring never starts OAuth or opens a browser. Renew an expired access token
// under the same process/file locks used by every normal ChatGPT request.
async fn restore_last(state: &ChatGptState, ai: &crate::ai::AiState) -> Result<Status, String> {
    let _op = state
        .operation
        .try_lock()
        .map_err(|_| "Another ChatGPT operation is running.")?;
    let _lock = state.lock()?;
    let mut r = state.registry()?;
    let inactive = |r, notice| {
        state.view(r, notice).map(|mut status| {
            status.active_id = None;
            status
        })
    };
    if !r.auto_restore {
        return inactive(r, String::new());
    }
    let id = r.last_account_id.clone().or_else(|| {
        // Existing profiles had no last-account field; migrate an unambiguous
        // single saved registration without choosing among multiple accounts.
        let candidates: Vec<_> = r
            .accounts
            .iter()
            .filter(|a| a.saved_session && a.plan_enabled && !a.reconsent_required)
            .collect();
        if candidates.len() == 1 {
            Some(candidates[0].id.clone())
        } else {
            None
        }
    });
    let Some(id) = id else {
        return inactive(r, String::new());
    };
    if !r
        .accounts
        .iter()
        .any(|a| a.id == id && a.saved_session && a.plan_enabled && !a.reconsent_required)
    {
        return inactive(r, "Sign in again to reconnect this ChatGPT account.".into());
    }
    let result = tokio::time::timeout(Duration::from_secs(20), fresh(state, &mut r, &id)).await;
    match result {
        Ok(Ok(c)) if c.enabled() => {
            state.activate(&mut r, &id)?;
            crate::ai::connect_chatgpt(ai, &id)?;
            state.view(r, String::new())
        }
        Ok(Ok(_)) => inactive(
            r,
            "This ChatGPT account needs plan authorization before use.".into(),
        ),
        Ok(Err(message)) => inactive(r, message),
        Err(_) => inactive(
            r,
            "ChatGPT reconnect timed out. The saved session is retained; retry when connected."
                .into(),
        ),
    }
}
pub async fn chatgpt_restore(
    state: &ChatGptState,
    ai: &crate::ai::AiState,
) -> Result<Status, String> {
    restore_last(&state, &ai).await
}
#[derive(Serialize)]
pub struct Model {
    slug: String,
    display_name: String,
}
pub async fn chatgpt_models(
    registration_id: String,
    state: &ChatGptState,
) -> Result<Vec<Model>, String> {
    let _op = state
        .operation
        .try_lock()
        .map_err(|_| "Another ChatGPT operation is running.")?;
    let _lock = state.lock()?;
    let mut r = state.registry()?;
    let c = fresh(&state, &mut r, &registration_id).await?;
    if !c.enabled() {
        return Err("ChatGPT plan permission is missing. Reauthorize this account.".into());
    }
    let response = client()?
        .get(format!("{RESOURCE}/models"))
        .bearer_auth(c.access_token)
        .send()
        .await
        .map_err(|_| "Could not fetch ChatGPT account models.")?;
    let status = response.status();
    let bytes = body(response, 1000000).await?;
    if !status.is_success() {
        return Err(api_error(status.as_u16(), &bytes));
    }
    let data: Value =
        serde_json::from_slice(&bytes).map_err(|_| "Invalid ChatGPT model catalog.")?;
    let models = data
        .get("models")
        .and_then(Value::as_array)
        .ok_or("ChatGPT did not return an account-specific model catalog.")?;
    Ok(models
        .iter()
        .filter(|m| m.get("visibility").and_then(Value::as_str) == Some("list"))
        .filter_map(|m| {
            let slug = m.get("slug")?.as_str()?;
            if slug.len() > 128
                || !slug
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"-_.:/".contains(&c))
            {
                return None;
            }
            Some(Model {
                slug: slug.into(),
                display_name: m
                    .get("display_name")
                    .and_then(Value::as_str)
                    .unwrap_or(slug)
                    .chars()
                    .take(256)
                    .collect(),
            })
        })
        .take(200)
        .collect())
}
fn api_error(status: u16, bytes: &[u8]) -> String {
    let data: Value = serde_json::from_slice(bytes).unwrap_or(Value::Null);
    let code = data
        .pointer("/error/code")
        .and_then(Value::as_str)
        .unwrap_or("");
    match code {"subscription_sharing_usage_limit_exceeded"|"subscription_sharing_usage_unavailable"=>"ChatGPT plan usage is unavailable or its limit has been reached. Try later or explicitly choose a different connection; no API-key fallback was used.".into(),"subscription_sharing_invalid_user"|"chatpass_v2_scope_not_authorized"|"chatpass_v2_invalid_authorization_context"=>"ChatGPT did not authorize this account/grant. Reauthorize the selected account.".into(),"subscription_sharing_user_unavailable"=>"ChatGPT account/workspace information is temporarily unavailable. Try later.".into(),_=>format!("ChatGPT returned HTTP {status}. Check account eligibility and model access. Your credentials were retained; no API-key fallback was used.")}
}
fn response_body(model: &str, system: &str, prompt: &str) -> Value {
    json!({"model":model,"instructions":system,"input":[{"role":"user","content":prompt}],"store":false,"stream":true})
}
#[derive(Default)]
struct Events {
    buffer: Vec<u8>,
    text: String,
    completed: bool,
    response: Option<Value>,
}
impl Events {
    fn push(&mut self, chunk: &[u8]) -> Result<(), String> {
        self.buffer.extend_from_slice(chunk);
        if self.buffer.len() > 1000000 {
            return Err("ChatGPT event buffer exceeded the size limit.".into());
        }
        while let Some(end) = self.buffer.iter().position(|b| *b == b'\n') {
            let bytes: Vec<_> = self.buffer.drain(..=end).collect();
            let line = std::str::from_utf8(&bytes)
                .map_err(|_| "ChatGPT stream contained invalid UTF-8.")?
                .trim_end_matches(['\r', '\n']);
            if let Some(data) = line.strip_prefix("data:") {
                let data = data.trim_start();
                if data == "[DONE]" {
                    continue;
                }
                let event: Value = serde_json::from_str(data)
                    .map_err(|_| "ChatGPT stream contained an invalid event.")?;
                match event.get("type").and_then(Value::as_str).unwrap_or("") {
                    "response.output_text.delta" => {
                        if let Some(delta) = event.get("delta").and_then(Value::as_str) {
                            self.text.push_str(delta);
                            if self.text.len() > 250000 {
                                return Err("ChatGPT text exceeded the size limit.".into());
                            }
                        }
                    }
                    "response.completed" => {
                        if event.pointer("/response/status").and_then(Value::as_str)
                            != Some("completed")
                        {
                            return Err("ChatGPT response did not complete.".into());
                        }
                        self.completed = true;
                        self.response = event.get("response").cloned();
                    }
                    "response.failed" | "response.incomplete" | "error" => {
                        let code = event
                            .pointer("/response/error/code")
                            .or_else(|| event.pointer("/error/code"))
                            .or_else(|| event.get("code"))
                            .and_then(Value::as_str)
                            .unwrap_or("");
                        return Err(api_error(
                            400,
                            &serde_json::to_vec(&json!({"error":{"code":code}}))
                                .unwrap_or_default(),
                        ));
                    }
                    _ => {}
                }
            }
        }
        Ok(())
    }
    fn finish(self) -> Result<Value, String> {
        if !self.completed || !self.buffer.iter().all(u8::is_ascii_whitespace) {
            return Err(
                "ChatGPT stream ended without completed inference. No proposal was accepted."
                    .into(),
            );
        }
        if let Some(r) = self.response {
            if r.get("output")
                .and_then(Value::as_array)
                .is_some_and(|a| !a.is_empty())
            {
                return Ok(r);
            }
        }
        Ok(
            json!({"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":self.text}]}]}),
        )
    }
}
pub(crate) async fn prepare(state: &ChatGptState, id: &str) -> Result<Credential, String> {
    let _op = state.operation.lock().await;
    let _lock = state.lock()?;
    let mut r = state.registry()?;
    let c = fresh(state, &mut r, id).await?;
    if !c.enabled() {
        return Err(
            "ChatGPT plan usage was not granted. Reauthorize the account before sending.".into(),
        );
    }
    Ok(c)
}
pub(crate) async fn send(
    c: Credential,
    model: &str,
    system: &str,
    prompt: &str,
    images: &[crate::images::Image],
) -> Result<Value, String> {
    let http = reqwest::Client::builder()
        .timeout(Duration::from_secs(120))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "Could not initialize ChatGPT transport.")?;
    let mut request_body = response_body(model, system, prompt);
    if !images.is_empty() { request_body["input"] = crate::images::responses_input(prompt, images); }
    let mut response = http
        .post(format!("{RESOURCE}/responses"))
        .bearer_auth(c.access_token)
        .json(&request_body)
        .send()
        .await
        .map_err(|_| "ChatGPT request failed or timed out. The service may count usage.")?;
    if !response.status().is_success() {
        let status = response.status().as_u16();
        return Err(api_error(status, &body(response, 250000).await?));
    }
    let mut events = Events::default();
    let mut count = 0;
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| "ChatGPT stream was interrupted. No proposal was accepted.")?
    {
        count += chunk.len();
        if count > 4000000 {
            return Err("ChatGPT stream exceeded the size limit.".into());
        }
        events.push(&chunk)?;
    }
    events.finish()
}
pub async fn chatgpt_sign_out(
    registration_id: String,
    state: &ChatGptState,
    ai: &crate::ai::AiState,
) -> Result<Status, String> {
    let _op = state
        .operation
        .try_lock()
        .map_err(|_| "Cancel the current ChatGPT operation before signing out.")?;
    let _lock = state.lock()?;
    let mut r = state.registry()?;
    let credential = state.load(&r, &registration_id).ok();
    let mut revoked = credential
        .as_ref()
        .is_some_and(|c| c.refresh_token.is_none());
    if let Some(refresh) = credential.as_ref().and_then(|c| c.refresh_token.as_ref()) {
        if let Ok(d) = discovery().await {
            if let Some(endpoint) = d.revocation_endpoint {
                for attempt in 0..3 {
                    let result = client()?
                        .post(&endpoint)
                        .timeout(Duration::from_secs(8))
                        .form(&[
                            ("token", refresh.as_str()),
                            ("token_type_hint", "refresh_token"),
                            ("client_id", registration_id.as_str()),
                        ])
                        .send()
                        .await;
                    if result.as_ref().is_ok_and(|r| r.status().as_u16() == 200) {
                        revoked = true;
                        break;
                    }
                    if result.as_ref().is_ok_and(|r| !r.status().is_server_error()) {
                        break;
                    }
                    tokio::time::sleep(Duration::from_millis(200 * (1 << attempt))).await;
                }
            }
        }
    }
    let was_active =
        state.active.lock().map_err(|_| io_error())?.as_deref() == Some(&registration_id);
    let warning = state.clear(&mut r, &registration_id)?;
    if was_active {
        crate::ai::disconnect_chatgpt(&ai, &registration_id)?;
    }
    let notice=[if revoked{"Signed out. Account registration is retained for later sign-in."}else{"Signed out locally. Remote session revocation was not confirmed; disconnect this app in ChatGPT Settings."},&warning].join(" ");
    state.view(r, notice)
}

#[cfg(test)]
mod tests {
    use super::*;
    use aws_lc_rs::{rsa::{KeyPair, KeySize}, signature::KeyPair as _};
    use std::sync::OnceLock;
    use std::sync::Arc;
    #[derive(Default, Clone)]
    struct MemoryVault {
        items: Arc<Mutex<HashMap<String, Vec<u8>>>>,
        fail: bool,
    }
    impl Vault for MemoryVault {
        fn read(&self, key: &str) -> Result<Vec<u8>, String> {
            self.items
                .lock()
                .unwrap()
                .get(key)
                .cloned()
                .ok_or("No synthetic credential".into())
        }
        fn write(&self, key: &str, value: &[u8]) -> Result<(), String> {
            if self.fail {
                return Err("Synthetic Keychain failure; session only".into());
            }
            self.items.lock().unwrap().insert(key.into(), value.into());
            Ok(())
        }
        fn delete(&self, key: &str) -> Result<(), String> {
            self.items.lock().unwrap().remove(key);
            Ok(())
        }
    }
    fn state(path: &PathBuf, vault: MemoryVault) -> ChatGptState {
        let mut s = ChatGptState::new(path.clone());
        s.vault = Box::new(vault);
        s
    }
    fn discovery_fixture() -> Discovery {
        Discovery {
            issuer: ISSUER.into(),
            authorization_endpoint: format!("{ISSUER}/api/accounts/authorize"),
            token_endpoint: format!("{ISSUER}/api/accounts/oauth/token"),
            jwks_uri: format!("{ISSUER}/.well-known/jwks.json"),
            revocation_endpoint: Some(format!("{ISSUER}/api/accounts/oauth/revoke")),
        }
    }
    fn claims() -> Value {
        json!({"iss":ISSUER,"sub":"synthetic-subject","aud":"oaiapp_test","nonce":"synthetic-nonce","iat":now(),"exp":now()+3600,"email":"same@example.invalid"})
    }
    // Fresh process-local test material: no private key is stored in the source tree.
    fn test_key() -> &'static KeyPair {
        static KEY: OnceLock<KeyPair> = OnceLock::new();
        KEY.get_or_init(|| KeyPair::generate(KeySize::Rsa2048).unwrap())
    }
    fn sign(claims: &Value) -> String {
        let header = json!({"alg":"RS256","typ":"JWT","kid":"synthetic-test-key"});
        let message = format!("{}.{}", URL_SAFE_NO_PAD.encode(serde_json::to_vec(&header).unwrap()),
            URL_SAFE_NO_PAD.encode(serde_json::to_vec(claims).unwrap()));
        let key = test_key();
        let mut signature = vec![0; key.public_modulus_len()];
        key.sign(&aws_lc_rs::signature::RSA_PKCS1_SHA256,
            &aws_lc_rs::rand::SystemRandom::new(), message.as_bytes(), &mut signature).unwrap();
        format!("{}.{}", message, URL_SAFE_NO_PAD.encode(signature))
    }
    fn jwks() -> JwkSet {
        let public = test_key().public_key();
        serde_json::from_value(json!({"keys":[{"kty":"RSA","alg":"RS256",
            "use":"sig","kid":"synthetic-test-key",
            "n":URL_SAFE_NO_PAD.encode(public.modulus().big_endian_without_leading_zero()),
            "e":URL_SAFE_NO_PAD.encode(public.exponent().big_endian_without_leading_zero())}]})).unwrap()
    }
    fn reg(id: &str, subject: &str) -> Registration {
        Registration {
            id: id.into(),
            subject: subject.into(),
            email: "same@example.invalid".into(),
            generation: 1,
            saved_session: false,
            plan_enabled: false,
            reconsent_required: false,
        }
    }
    fn raw() -> TokenResponse {
        serde_json::from_value(json!({"access_token":"SYNTHETIC_ACCESS","refresh_token":"SYNTHETIC_REFRESH","id_token":"SYNTHETIC_ID","token_type":"Bearer","expires_in":3600,"scope":SCOPES})).unwrap()
    }
    #[test]
    fn authorization_uses_pkce_host_identity_and_exact_loopback_callback() {
        let mut t = Transaction::new(54321, None).unwrap();
        t.verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk".into();
        let url = reqwest::Url::parse(
            &t.authorize(&discovery_fixture(), "urn:uuid:synthetic-host")
                .unwrap(),
        )
        .unwrap();
        let q: BTreeMap<_, _> = url
            .query_pairs()
            .map(|(k, v)| (k.into_owned(), v.into_owned()))
            .collect();
        assert_eq!(q["client_id"], "dynamic_agent_client");
        assert_eq!(q["agent_name_hint"], "PyMOL AI-Assistant");
        assert_eq!(q["redirect_uri"], "http://127.0.0.1:54321/auth/callback");
        assert_eq!(
            q["code_challenge"],
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        );
        assert_eq!(q["resource"], RESOURCE);
        assert!(!q.contains_key("code_verifier"));
        t.client_id = Some("oaiapp_test".into());
        let returning = t.authorize(&discovery_fixture(), "host").unwrap();
        assert!(!returning.contains("agent_name_hint"));
        assert!(returning.contains("client_id=oaiapp_test"));
        assert_ne!(t.state, Transaction::new(54321, None).unwrap().state);
        assert_eq!(host_id().unwrap().len(), 45);
    }
    #[test]
    fn callback_rejects_changed_state_duplicates_client_substitution_and_denial() {
        let mut t = Transaction::new(54321, None).unwrap();
        t.state = "expected".into();
        assert!(callback(
            "/auth/callback?state=expected&code=test&client_id=oaiapp_test",
            &t
        )
        .is_ok());
        for target in [
            "/auth/callback?state=wrong&code=test&client_id=oaiapp_test",
            "/auth/callback?state=expected&state=expected&code=test&client_id=oaiapp_test",
            "/auth/callback?state=expected&code=test",
            "/auth/callback?state=expected&code=test&client_id=dynamic_agent_client",
            "/auth/callback?state=expected&error=access_denied",
            "/callback?state=expected&code=test&client_id=oaiapp_test",
        ] {
            assert!(callback(target, &t).is_err());
        }
        t.client_id = Some("oaiapp_test".into());
        assert!(callback("/auth/callback?state=expected&code=test", &t).is_ok());
        assert!(callback(
            "/auth/callback?state=expected&code=test&client_id=oaiapp_other",
            &t
        )
        .is_err());
    }
    #[test]
    fn identity_signature_issuer_audience_nonce_subject_and_time_are_verified() {
        let original = claims();
        let token = sign(&original);
        assert!(verify_identity(
            &token,
            &jwks(),
            "oaiapp_test",
            Some("synthetic-nonce"),
            Some("synthetic-subject")
        )
        .is_ok());
        for (key, value) in [
            ("iss", json!("https://untrusted.invalid")),
            ("aud", json!("oaiapp_other")),
            ("nonce", json!("wrong")),
            ("sub", json!("other-subject")),
            ("exp", json!(now() - 100)),
            ("iat", json!(now() + 100)),
        ] {
            let mut c = original.clone();
            c[key] = value;
            assert!(
                verify_identity(
                    &sign(&c),
                    &jwks(),
                    "oaiapp_test",
                    Some("synthetic-nonce"),
                    Some("synthetic-subject")
                )
                .is_err(),
                "{key}"
            );
        }
        let mut c = original.clone();
        c["aud"] = json!(["oaiapp_test", "oaiapp_other"]);
        assert!(verify_identity(
            &sign(&c),
            &jwks(),
            "oaiapp_test",
            Some("synthetic-nonce"),
            None
        )
        .is_err());
        c["azp"] = json!("oaiapp_test");
        assert!(verify_identity(
            &sign(&c),
            &jwks(),
            "oaiapp_test",
            Some("synthetic-nonce"),
            None
        )
        .is_ok());
        let mut forged = token.into_bytes();
        let last = forged.len() - 8;
        forged[last] = if forged[last] == b'A' { b'B' } else { b'A' };
        assert!(verify_identity(
            &String::from_utf8(forged).unwrap(),
            &jwks(),
            "oaiapp_test",
            None,
            None
        )
        .is_err());
        let mut bad_jwks = jwks();
        bad_jwks.keys[0].common.key_algorithm = Some(jsonwebtoken::jwk::KeyAlgorithm::RS512);
        assert!(verify_identity(&sign(&original), &bad_jwks, "oaiapp_test", None, None).is_err());
    }
    #[test]
    fn account_registry_has_no_tokens_and_does_not_merge_matching_emails() {
        let dir = tempfile::tempdir().unwrap();
        let s = state(&dir.path().to_path_buf(), MemoryVault::default());
        let _guard = s.lock().unwrap();
        let mut r = s.registry().unwrap();
        let host = r.host_id.clone();
        r.accounts.push(reg("oaiapp_first", "first"));
        r.accounts.push(reg("oaiapp_second", "second"));
        for (id, subject) in [("oaiapp_first", "first"), ("oaiapp_second", "second")] {
            let c = credential(raw(), id, subject, &host, 1, None).unwrap();
            s.store(&mut r, c).unwrap();
            assert_eq!(s.load(&r, id).unwrap().subject, subject);
        }
        assert_eq!(s.registry().unwrap().host_id, host);
        let metadata = fs::read_to_string(dir.path().join("accounts.json")).unwrap();
        for secret in ["SYNTHETIC_ACCESS", "SYNTHETIC_REFRESH", "SYNTHETIC_ID"] {
            assert!(!metadata.contains(secret));
        }
        let status = serde_json::to_string(&s.view(r, String::new()).unwrap()).unwrap();
        assert!(!status.contains("token"));
        assert!(!status.contains("SYNTHETIC"));
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(dir.path().join("accounts.json"))
                    .unwrap()
                    .permissions()
                    .mode()
                    & 0o777,
                0o600
            );
        }
        assert!(s.lock().is_err());
    }
    #[test]
    fn keychain_failure_keeps_only_session_memory_and_signout_is_account_scoped() {
        let dir = tempfile::tempdir().unwrap();
        let s = state(
            &dir.path().to_path_buf(),
            MemoryVault {
                fail: true,
                ..Default::default()
            },
        );
        let _guard = s.lock().unwrap();
        let mut r = s.registry().unwrap();
        r.accounts.push(reg("oaiapp_first", "first"));
        r.accounts.push(reg("oaiapp_second", "second"));
        for (id, subject) in [("oaiapp_first", "first"), ("oaiapp_second", "second")] {
            let c = credential(raw(), id, subject, &r.host_id, 1, None).unwrap();
            assert!(s.store(&mut r, c).unwrap().contains("session only"));
        }
        assert!(!r.accounts[0].saved_session);
        s.clear(&mut r, "oaiapp_first").unwrap();
        assert!(s.load(&r, "oaiapp_first").is_err());
        assert!(s.load(&r, "oaiapp_second").is_ok());
        assert_eq!(r.accounts[0].id, "oaiapp_first");
        let reloaded = state(&dir.path().to_path_buf(), MemoryVault::default());
        assert!(reloaded.load(&r, "oaiapp_second").is_err());
    }
    #[test]
    fn identity_only_permission_is_retained_but_cannot_enable_plan_inference() {
        let c = credential(
            serde_json::from_value(
                json!({"id_token":"SYNTHETIC_ID","scope":"openid profile email"}),
            )
            .unwrap(),
            "oaiapp_test",
            "subject",
            "host",
            1,
            None,
        )
        .unwrap();
        assert!(!c.enabled());
        let old = credential(raw(), "oaiapp_test", "subject", "host", 1, None).unwrap();
        let mut replacement = raw();
        replacement.access_token = "NEW_ACCESS".into();
        replacement.refresh_token = Some("NEW_REFRESH".into());
        replacement.id_token = None;
        replacement.scope = None;
        let new = credential(replacement, "oaiapp_test", "subject", "host", 1, Some(&old)).unwrap();
        assert_eq!(new.refresh_token.as_deref(), Some("NEW_REFRESH"));
        assert_eq!(new.id_token, old.id_token);
        assert!(new.enabled());
        let (error, terminal) = token_error(400, br#"{"error":"invalid_grant"}"#, true);
        assert!(terminal);
        assert!(!error.contains("invalid_grant"));
        assert!(!token_error(503, br#"{"error":"temporary"}"#, true).1);
    }
    #[test]
    fn chatgpt_inference_uses_only_supported_plan_fields() {
        let b = response_body("model", "instructions", "context");
        assert_eq!(b["store"], false);
        assert_eq!(b["stream"], true);
        assert!(b["input"].is_array());
        for key in [
            "max_output_tokens",
            "temperature",
            "previous_response_id",
            "background",
            "conversation",
            "tools",
        ] {
            assert!(b.get(key).is_none());
        }
    }
    #[test]
    fn stream_handles_arbitrary_chunks_and_requires_terminal_success() {
        let stream="event: response.output_text.delta\r\ndata: {\"type\":\"response.output_text.delta\",\"delta\":\"héllo\"}\r\n\r\ndata: {\"type\":\"response.completed\",\"response\":{\"status\":\"completed\"}}\n\ndata: [DONE]\n\n";
        let mut events = Events::default();
        for chunk in stream.as_bytes().chunks(3) {
            events.push(chunk).unwrap();
        }
        assert_eq!(
            events.finish().unwrap()["output"][0]["content"][0]["text"],
            "héllo"
        );
        let mut incomplete = Events::default();
        incomplete
            .push(b"data: {\"type\":\"response.output_text.delta\",\"delta\":\"partial\"}\n\n")
            .unwrap();
        assert!(incomplete.finish().is_err());
        let mut failed = Events::default();
        assert!(failed.push(b"data: {\"type\":\"response.failed\",\"response\":{\"error\":{\"code\":\"subscription_sharing_usage_limit_exceeded\"}}}\n\n").unwrap_err().contains("no API-key fallback"));
    }
    #[test]
    fn discovery_and_diagnostics_never_accept_third_party_auth_hosts() {
        let mut d = discovery_fixture();
        assert!(validate_discovery(&d).is_ok());
        d.jwks_uri = "https://untrusted.invalid/keys".into();
        assert!(validate_discovery(&d).is_err());
        let e = api_error(401, br#"{"detail":"SYNTHETIC_SECRET"}"#);
        assert!(!e.contains("SYNTHETIC_SECRET"));
    }
    #[tokio::test(flavor = "current_thread")]
    async fn actual_loopback_callback_uses_only_its_bound_host_and_port() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let mut t = Transaction::new(port, None).unwrap();
        t.state = "synthetic-state".into();
        let task = tokio::spawn(async move { receive(listener, &t).await });
        let mut stream = tokio::net::TcpStream::connect(("127.0.0.1", port))
            .await
            .unwrap();
        let request=format!("GET /auth/callback?state=synthetic-state&code=synthetic-code&client_id=oaiapp_test HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n");
        stream.write_all(request.as_bytes()).await.unwrap();
        let mut bytes = Vec::new();
        stream.read_to_end(&mut bytes).await.unwrap();
        assert!(!String::from_utf8(bytes).unwrap().contains("synthetic-code"));
        assert_eq!(task.await.unwrap().unwrap().client_id, "oaiapp_test");
    }
}

#[cfg(test)]
mod reconnect_tests {
    use super::*;
    fn registration(id: &str) -> Registration {
        Registration {
            id: id.into(),
            subject: format!("subject-{id}"),
            email: "synthetic@example.invalid".into(),
            generation: 1,
            saved_session: false,
            plan_enabled: false,
            reconsent_required: false,
        }
    }
    fn saved(state: &ChatGptState, r: &mut Registry, id: &str) -> Credential {
        r.accounts.push(registration(id));
        let c = Credential {
            client_id: id.into(),
            subject: format!("subject-{id}"),
            host_id: r.host_id.clone(),
            generation: 1,
            access_token: "SYNTHETIC_ACCESS".into(),
            refresh_token: Some("SYNTHETIC_REFRESH".into()),
            id_token: "SYNTHETIC_ID".into(),
            scopes: SCOPES.split_whitespace().map(str::to_string).collect(),
            expires_at: now() + 3600,
            earliest_refresh_at: None,
        };
        assert_eq!(state.store(r, c.clone()).unwrap(), "");
        c
    }
    #[tokio::test]
    async fn disk_sessions_restore_the_last_account_after_restart_without_login_or_inference() {
        let dir = tempfile::tempdir().unwrap();
        let first = ChatGptState::new(dir.path().into());
        let host;
        {
            let _lock = first.lock().unwrap();
            let mut r = first.registry().unwrap();
            host = r.host_id.clone();
            saved(&first, &mut r, "oaiapp_first");
            saved(&first, &mut r, "oaiapp_second");
            first.activate(&mut r, "oaiapp_second").unwrap();
        }
        let restarted = ChatGptState::new(dir.path().into());
        let ai = crate::ai::AiState::default();
        let status = restore_last(&restarted, &ai).await.unwrap();
        assert_eq!(status.active_id.as_deref(), Some("oaiapp_second"));
        let r = restarted.registry().unwrap();
        assert_eq!(r.host_id, host);
        assert_eq!(
            restarted.load(&r, "oaiapp_second").unwrap().access_token,
            "SYNTHETIC_ACCESS"
        );
        let metadata = fs::read_to_string(dir.path().join("accounts.json")).unwrap();
        let public = serde_json::to_string(&status).unwrap();
        assert!(!metadata.contains("SYNTHETIC"));
        assert!(!public.contains("SYNTHETIC"));
        assert!(!public.contains("refresh_token"));
    }
    #[tokio::test]
    async fn explicit_signout_cannot_restore_a_different_saved_account() {
        let dir = tempfile::tempdir().unwrap();
        let state = ChatGptState::new(dir.path().into());
        {
            let _lock = state.lock().unwrap();
            let mut r = state.registry().unwrap();
            saved(&state, &mut r, "oaiapp_first");
            saved(&state, &mut r, "oaiapp_second");
            state.activate(&mut r, "oaiapp_first").unwrap();
            state.clear(&mut r, "oaiapp_first").unwrap();
        }
        let restarted = ChatGptState::new(dir.path().into());
        let ai = crate::ai::AiState::default();
        assert!(restore_last(&restarted, &ai)
            .await
            .unwrap()
            .active_id
            .is_none());
        let r = restarted.registry().unwrap();
        assert!(!r.auto_restore);
        assert!(restarted.load(&r, "oaiapp_first").is_err());
        assert!(restarted.load(&r, "oaiapp_second").is_ok());
    }
    #[tokio::test]
    async fn older_single_account_profiles_migrate_but_ambiguous_profiles_are_not_guessed() {
        let dir = tempfile::tempdir().unwrap();
        let state = ChatGptState::new(dir.path().into());
        {
            let _lock = state.lock().unwrap();
            let mut r = state.registry().unwrap();
            saved(&state, &mut r, "oaiapp_first");
            let mut old = serde_json::to_value(&r).unwrap();
            old.as_object_mut().unwrap().remove("last_account_id");
            old.as_object_mut().unwrap().remove("auto_restore");
            fs::write(
                dir.path().join("accounts.json"),
                serde_json::to_vec(&old).unwrap(),
            )
            .unwrap();
        }
        let ai = crate::ai::AiState::default();
        assert_eq!(
            restore_last(&state, &ai)
                .await
                .unwrap()
                .active_id
                .as_deref(),
            Some("oaiapp_first")
        );
        {
            let _lock = state.lock().unwrap();
            let mut r = state.registry().unwrap();
            saved(&state, &mut r, "oaiapp_second");
            r.last_account_id = None;
            state.save(&r).unwrap();
        }
        let restarted = ChatGptState::new(dir.path().into());
        assert!(restore_last(&restarted, &ai)
            .await
            .unwrap()
            .active_id
            .is_none());
    }
    #[tokio::test]
    async fn deferred_renewal_retains_the_session_and_missing_refresh_requests_reauthorization() {
        let dir = tempfile::tempdir().unwrap();
        let state = ChatGptState::new(dir.path().into());
        {
            let _lock = state.lock().unwrap();
            let mut r = state.registry().unwrap();
            let mut c = saved(&state, &mut r, "oaiapp_first");
            c.expires_at = now() - 1;
            c.earliest_refresh_at = Some(now() + 600);
            state.store(&mut r, c).unwrap();
            state.activate(&mut r, "oaiapp_first").unwrap();
        }
        let ai = crate::ai::AiState::default();
        let status = restore_last(&state, &ai).await.unwrap();
        assert!(status.active_id.is_none());
        assert!(status.notice.contains("later token renewal"));
        {
            let _lock = state.lock().unwrap();
            let mut r = state.registry().unwrap();
            assert!(r.auto_restore);
            let mut c = state.load(&r, "oaiapp_first").unwrap();
            assert!(c.refresh_token.is_some());
            c.earliest_refresh_at = None;
            c.refresh_token = None;
            state.store(&mut r, c).unwrap();
        }
        let status = restore_last(&state, &ai).await.unwrap();
        assert!(status.active_id.is_none());
        assert!(status.notice.contains("Sign in again"));
    }
    #[tokio::test]
    async fn refreshed_tokens_rotate_and_survive_a_new_native_process_state() {
        let dir = tempfile::tempdir().unwrap();
        let state = ChatGptState::new(dir.path().into());
        let _lock = state.lock().unwrap();
        let mut r = state.registry().unwrap();
        let mut old = saved(&state, &mut r, "oaiapp_first");
        old.expires_at = now() - 1;
        state.store(&mut r, old.clone()).unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut bytes = Vec::new();
            let mut chunk = [0; 4096];
            loop {
                let n = socket.read(&mut chunk).await.unwrap();
                assert!(n > 0);
                bytes.extend_from_slice(&chunk[..n]);
                assert!(bytes.len() < 65536);
                if let Some(at) = bytes.windows(4).position(|b| b == b"\r\n\r\n") {
                    let header = String::from_utf8_lossy(&bytes[..at]);
                    let length: usize = header
                        .lines()
                        .find_map(|line| {
                            line.split_once(':')
                                .filter(|(k, _)| k.eq_ignore_ascii_case("content-length"))
                                .map(|(_, v)| v.trim().parse().unwrap())
                        })
                        .unwrap();
                    if bytes.len() >= at + 4 + length {
                        break;
                    }
                }
            }
            let request = String::from_utf8(bytes).unwrap();
            assert!(request.starts_with("POST /token "));
            assert!(request.contains("grant_type=refresh_token"));
            assert!(request.contains("refresh_token=SYNTHETIC_REFRESH"));
            let body = r#"{"access_token":"SYNTHETIC_ROTATED_ACCESS","refresh_token":"SYNTHETIC_ROTATED_REFRESH","token_type":"Bearer","expires_in":3600}"#;
            socket.write_all(format!("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",body.len(),body).as_bytes()).await.unwrap();
        });
        let discovery = Discovery {
            issuer: ISSUER.into(),
            authorization_endpoint: format!("{ISSUER}/authorize"),
            token_endpoint: format!("http://{address}/token"),
            jwks_uri: format!("{ISSUER}/jwks"),
            revocation_endpoint: None,
        };
        let updated = renew_with_discovery(
            &state,
            &mut r,
            "oaiapp_first",
            old,
            "SYNTHETIC_REFRESH".into(),
            &discovery,
        )
        .await
        .unwrap();
        server.await.unwrap();
        assert_eq!(
            updated.refresh_token.as_deref(),
            Some("SYNTHETIC_ROTATED_REFRESH")
        );
        assert_eq!(updated.id_token, "SYNTHETIC_ID");
        state.activate(&mut r, "oaiapp_first").unwrap();
        drop(_lock);
        let restarted = ChatGptState::new(dir.path().into());
        let status = restore_last(&restarted, &crate::ai::AiState::default())
            .await
            .unwrap();
        assert!(status.active_id.is_some());
        let saved = restarted
            .load(&restarted.registry().unwrap(), "oaiapp_first")
            .unwrap();
        assert_eq!(saved.access_token, "SYNTHETIC_ROTATED_ACCESS");
        assert_eq!(saved.refresh_token, updated.refresh_token);
    }
}

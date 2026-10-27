// Adapted from PlasmidCraft (MIT); see licenses/PlasmidCraft-AI-MIT.txt.
//! Opt-in AI HTTP transport. Credentials stay native, optionally persisted in the device vault.
#[path = "ai_models.rs"]
mod models;
use crate::ai_vault::{DeviceVault, Vault};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{sync::Mutex, time::Duration};
use crate::Host;
use tokio::sync::watch;

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Connection {
    provider: String,
    endpoint: String,
    api_key: String,
    #[serde(default)]
    account_id: Option<String>,
}
#[derive(Default)]
pub struct Session {
    connection: Option<Connection>,
    cancel: Option<watch::Sender<bool>>,
    generation: u64,
}
pub type AiState = Mutex<Session>;
pub(crate) fn open_url(url: &str) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    let result = std::process::Command::new("open").arg(url).spawn();
    #[cfg(target_os = "windows")]
    let result = std::process::Command::new("rundll32.exe")
        .args(["url.dll,FileProtocolHandler", url])
        .spawn();
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let result = std::process::Command::new("xdg-open").arg(url).spawn();
    result
        .map(|_| ())
        .map_err(|_| "Could not open the AI website in your browser.".into())
}
pub(crate) fn connect_chatgpt(state: &AiState, id: &str) -> Result<(), String> {
    let mut s = state.lock().map_err(|_| "AI connection unavailable.")?;
    if let Some(cancel) = s.cancel.take() {
        let _ = cancel.send(true);
    }
    s.generation += 1;
    s.connection = Some(Connection {
        provider: "chatgpt".into(),
        endpoint: "https://api.openai.com/v1".into(),
        api_key: String::new(),
        account_id: Some(id.into()),
    });
    Ok(())
}
pub(crate) fn disconnect_chatgpt(state: &AiState, id: &str) -> Result<(), String> {
    let mut s = state.lock().map_err(|_| "AI connection unavailable.")?;
    if s.connection
        .as_ref()
        .is_some_and(|c| c.provider == "chatgpt" && c.account_id.as_deref() == Some(id))
    {
        if let Some(cancel) = s.cancel.take() {
            let _ = cancel.send(true);
        }
        s.generation += 1;
        s.connection = None;
    }
    Ok(())
}
#[derive(Serialize)]
pub struct Connected {
    provider: String,
    endpoint: String,
    model: String,
    remembered: bool,
}
#[derive(Deserialize, Serialize)]
struct SavedConnection {
    version: u8,
    connection: Connection,
    model: String,
}
fn validate(mut c: Connection) -> Result<Connection, String> {
    c.endpoint = c.endpoint.trim_end_matches('/').to_string();
    let fixed = match c.provider.as_str() {
        "openai" => Some("https://api.openai.com/v1"),
        "anthropic" => Some("https://api.anthropic.com/v1"),
        "gemini" => Some("https://generativelanguage.googleapis.com/v1beta"),
        "compatible" => None,
        _ => return Err("Unknown AI provider.".into()),
    };
    if let Some(endpoint) = fixed {
        if c.endpoint != endpoint {
            return Err("Use the official endpoint for this provider.".into());
        }
    }
    let url = reqwest::Url::parse(&c.endpoint).map_err(|_| "Invalid API base URL.")?;
    let local = matches!(
        url.host_str(),
        Some("127.0.0.1" | "localhost" | "[::1]" | "::1")
    );
    if !(url.scheme() == "https" || (url.scheme() == "http" && local))
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
    {
        return Err(
            "Use HTTPS, or HTTP on localhost, without URL credentials, queries or fragments."
                .into(),
        );
    }
    if c.api_key.len() > 8192 || c.api_key.chars().any(char::is_control) {
        return Err("Invalid API credential.".into());
    }
    if fixed.is_some() && c.api_key.trim().is_empty() {
        return Err("Enter your provider API key.".into());
    }
    Ok(c)
}
fn install_connection(
    connection: Connection,
    model: String,
    remembered: bool,
    state: &AiState,
) -> Result<Connected, String> {
    let out = Connected {
        provider: connection.provider.clone(),
        endpoint: connection.endpoint.clone(),
        model,
        remembered,
    };
    let mut s = state.lock().map_err(|_| "AI connection unavailable.")?;
    if let Some(cancel) = s.cancel.take() {
        let _ = cancel.send(true);
    }
    s.generation += 1;
    s.connection = Some(connection);
    Ok(out)
}
fn save_connection(vault: &dyn Vault, connection: &Connection, model: &str) -> Result<(), String> {
    if model.trim().is_empty() || model.len() > 256 || model.chars().any(char::is_control) {
        return Err("Choose a model before remembering this connection.".into());
    }
    let saved = SavedConnection {
        version: 1,
        connection: connection.clone(),
        model: model.into(),
    };
    let bytes =
        serde_json::to_vec(&saved).map_err(|_| "Could not prepare the saved API connection.")?;
    vault.write(&bytes)
}
fn restore_connection(vault: &dyn Vault, state: &AiState) -> Result<Option<Connected>, String> {
    let Some(bytes) = vault.read()? else {
        return Ok(None);
    };
    let saved: SavedConnection = serde_json::from_slice(&bytes).map_err(|_| {
        "The saved API connection is invalid. Forget it in AI → Accounts and Models and reconnect."
    })?;
    if saved.version != 1
        || saved.model.trim().is_empty()
        || saved.model.len() > 256
        || saved.model.chars().any(char::is_control)
    {
        return Err("The saved API connection is unsupported. Forget it and reconnect.".into());
    }
    let connection = validate(saved.connection)?;
    install_connection(connection, saved.model, true, state).map(Some)
}
fn device_vault(app: &Host) -> Result<DeviceVault, String> {
    let directory = app.directory.clone();
    Ok(DeviceVault::new(
        directory.join("api").join("connection.json"),
    ))
}
pub fn ai_connect(
    app: Host,
    connection: Connection,
    remember: Option<bool>,
    model: Option<String>,
    state: &AiState,
) -> Result<Connected, String> {
    let connection = validate(connection)?;
    let remember = remember.unwrap_or(true);
    let model = model.unwrap_or_default();
    if remember {
        save_connection(&device_vault(&app)?, &connection, &model)?;
    }
    install_connection(connection, model, remember, &state)
}
pub async fn ai_list_models(
    connection: Option<Connection>,
    state: &AiState,
) -> Result<models::ModelList, String> {
    let connection = match connection {
        Some(connection) => connection,
        None => state
            .lock()
            .map_err(|_| "AI connection unavailable.")?
            .connection
            .clone()
            .ok_or("Enter an API key or connect a provider first.")?,
    };
    tokio::time::timeout(Duration::from_secs(20), models::list(connection))
        .await
        .map_err(|_| "Model discovery timed out. Retry or enter a model ID manually.".to_string())?
}
pub fn ai_restore_saved(
    app: Host,
    state: &AiState,
) -> Result<Option<Connected>, String> {
    restore_connection(&device_vault(&app)?, &state)
}
pub fn ai_forget_saved(app: Host, state: &AiState) -> Result<(), String> {
    // Only report success after deletion; keep the active session if the vault refuses.
    if active_provider(state).as_deref()==Some("chatgpt") {device_vault(&app)?.delete()} else {forget_saved_connection(&device_vault(&app)?, &state)}
}
pub fn ai_disconnect(state: &AiState) -> Result<(), String> {
    disconnect(&state)
}
fn forget_saved_connection(vault: &dyn Vault, state: &AiState) -> Result<(), String> {
    vault.delete()?;
    disconnect(state)
}
fn disconnect(state: &AiState) -> Result<(), String> {
    let mut s = state.lock().map_err(|_| "AI connection unavailable.")?;
    if let Some(cancel) = s.cancel.take() {
        let _ = cancel.send(true);
    }
    s.generation += 1;
    s.connection = None;
    Ok(())
}
pub fn ai_cancel(state: &AiState) -> Result<(), String> {
    let mut s = state.lock().map_err(|_| "AI connection unavailable.")?;
    if let Some(cancel) = s.cancel.take() {
        let _ = cancel.send(true);
    }
    s.generation += 1;
    Ok(())
}
fn request_body(provider: &str, model: &str, system: &str, prompt: &str) -> Value {
    match provider {
        "openai" => {
            json!({"model":model,"instructions":system,"input":prompt,"max_output_tokens":8192,"store":false})
        }
        "anthropic" => {
            json!({"model":model,"system":system,"max_tokens":8192,"messages":[{"role":"user","content":prompt}]})
        }
        "gemini" => {
            json!({"systemInstruction":{"parts":[{"text":system}]},"contents":[{"role":"user","parts":[{"text":prompt}]}],"generationConfig":{"maxOutputTokens":8192}})
        }
        _ => {
            json!({"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":prompt}],"max_tokens":8192,"stream":false})
        }
    }
}
fn image_request_body(provider: &str, model: &str, system: &str, prompt: &str, images: &[crate::images::Image]) -> Value {
    let mut body = request_body(provider, model, system, prompt);
    if images.is_empty() { return body; }
    match provider {
        "openai" => body["input"] = crate::images::responses_input(prompt, images),
        "anthropic" => {
            let mut content = vec![json!({"type":"text","text":prompt})];
            for image in images { content.push(json!({"type":"image","source":{"type":"base64","media_type":image.mime,"data":image.data}})); }
            body["messages"][0]["content"] = json!(content);
        },
        "gemini" => {
            let mut parts = vec![json!({"text":prompt})];
            for image in images { parts.push(json!({"inlineData":{"mimeType":image.mime,"data":image.data}})); }
            body["contents"][0]["parts"] = json!(parts);
        },
        _ => {
            let mut content = vec![json!({"type":"text","text":prompt})];
            for image in images { content.push(json!({"type":"image_url","image_url":{"url":image.url}})); }
            body["messages"][1]["content"] = json!(content);
        }
    }
    body
}
async fn send(c: &Connection, model: &str, system: &str, prompt: &str, images: &[crate::images::Image]) -> Result<Value, String> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(120))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "Could not initialize AI transport.")?;
    let suffix = match c.provider.as_str() {
        "openai" => "/responses".to_string(),
        "anthropic" => "/messages".to_string(),
        "gemini" => format!("/models/{model}:generateContent"),
        _ => "/chat/completions".to_string(),
    };
    let mut request = client
        .post(format!("{}{suffix}", c.endpoint))
        .json(&image_request_body(&c.provider, model, system, prompt, images));
    match c.provider.as_str() {
        "anthropic" => {
            request = request
                .header("x-api-key", &c.api_key)
                .header("anthropic-version", "2023-06-01");
        }
        "gemini" => {
            request = request.header("x-goog-api-key", &c.api_key);
        }
        _ => {
            if !c.api_key.is_empty() {
                request = request.bearer_auth(&c.api_key);
            }
        }
    }
    let mut response = request.send().await.map_err(|e| {
        if e.is_timeout() {
            "AI request timed out. The provider may have processed it."
        } else {
            "Could not contact the AI endpoint. Check connection and API base URL."
        }
    })?;
    let status = response.status();
    if !status.is_success() {
        return Err(match status.as_u16() {
            401 | 403 => {
                "AI authentication/access failed. Check the API key and model access.".into()
            }
            429 => {
                "AI usage or rate limit reached. Check the provider account and try later.".into()
            }
            _ => format!(
                "AI provider returned HTTP {}. Check model access/settings; window inspection requires a model that accepts images.",
                status.as_u16()
            ),
        });
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| "AI response was interrupted.")?
    {
        if bytes.len() + chunk.len() > 1_000_000 {
            return Err("AI response exceeds the 1 MB limit.".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&bytes)
        .map_err(|_| "Provider returned invalid JSON. Check the API protocol/base URL.".into())
}
pub async fn ai_request(
    model: String,
    system: String,
    prompt: String,
    images: Vec<crate::images::Image>,
    state: &AiState,
    chatgpt: &crate::chatgpt::ChatGptState,
) -> Result<Value, String> {
    if model.is_empty()
        || model.len() > 128
        || !model
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "-_.:/".contains(c))
        || model.contains("..")
    {
        return Err("Enter a valid provider model ID.".into());
    }
    // Gemini model is a URL path segment. Other providers may use namespaced IDs.
    if prompt.len() > 500_000 || system.len() > 20_000 {
        return Err("AI request exceeds the context limit.".into());
    }
    let (c, mut cancel, generation) = {
        let mut s = state.lock().map_err(|_| "AI connection unavailable.")?;
        if s.cancel.is_some() {
            return Err("An AI request is already running. Cancel it first.".into());
        }
        let c = s
            .connection
            .clone()
            .ok_or("Connect an AI provider first.")?;
        if c.provider == "gemini" && model.contains(['/', ':']) {
            return Err("Use the Gemini model ID without models/ prefix.".into());
        }
        let (tx, rx) = watch::channel(false);
        s.cancel = Some(tx);
        s.generation += 1;
        (c, rx, s.generation)
    };
    // Complete a rotating-token renewal even when a user cancels inference.
    let prepared = if c.provider == "chatgpt" {
        Some(crate::chatgpt::prepare(&chatgpt, c.account_id.as_deref().unwrap_or("")).await)
    } else {
        None
    };
    let result = if *cancel.borrow() {
        Err("AI request canceled. The provider may still count usage.".into())
    } else if let Some(prepared) = prepared {
        match prepared {
            Ok(credential) => {
                tokio::select! {value=crate::chatgpt::send(credential,&model,&system,&prompt,&images)=>value,_=cancel.changed()=>Err("AI request canceled. The provider may still count usage.".into())}
            }
            Err(error) => Err(error),
        }
    } else {
        tokio::select! { value=send(&c,&model,&system,&prompt,&images)=>value, _=cancel.changed()=>Err("AI request canceled. The provider may still count usage.".into()) }
    };
    if let Ok(mut s) = state.lock() {
        if s.generation == generation {
            s.cancel = None;
        }
    }
    result
}
#[cfg(test)]
mod tests {
    use super::*;
    #[derive(Default)]
    struct MemoryVault {
        bytes: Mutex<Option<Vec<u8>>>,
        fail_write: bool,
        fail_delete: bool,
    }
    impl Vault for MemoryVault {
        fn read(&self) -> Result<Option<Vec<u8>>, String> {
            Ok(self.bytes.lock().unwrap().clone())
        }
        fn write(&self, value: &[u8]) -> Result<(), String> {
            if self.fail_write {
                return Err("Synthetic secure-store failure".into());
            }
            *self.bytes.lock().unwrap() = Some(value.to_vec());
            Ok(())
        }
        fn delete(&self) -> Result<(), String> {
            if self.fail_delete {
                return Err("Synthetic deletion failure".into());
            }
            *self.bytes.lock().unwrap() = None;
            Ok(())
        }
    }
    #[test]
    fn inspection_images_use_provider_content_blocks() {
        let images = crate::images::parse(&json!(["data:image/jpeg;base64,/9j/"])).unwrap();
        let a = image_request_body("openai", "m", "s", "p", &images);
        assert_eq!(a["input"][0]["content"][1]["type"], "input_image");
        let a = image_request_body("anthropic", "m", "s", "p", &images);
        assert_eq!(a["messages"][0]["content"][1]["source"]["data"], "/9j/");
        let a = image_request_body("gemini", "m", "s", "p", &images);
        assert_eq!(a["contents"][0]["parts"][1]["inlineData"]["mimeType"], "image/jpeg");
        let a = image_request_body("compatible", "m", "s", "p", &images);
        assert_eq!(a["messages"][1]["content"][1]["image_url"]["url"], images[0].url);
    }
    #[test]
    fn saved_api_connection_restores_natively_without_returning_the_key() {
        let vault = MemoryVault::default();
        let first = AiState::default();
        assert!(restore_connection(&vault, &first).unwrap().is_none());
        let connection = validate(c("openai", "https://api.openai.com/v1")).unwrap();
        save_connection(&vault, &connection, "selected-model").unwrap();
        let restarted = AiState::default();
        let restored = restore_connection(&vault, &restarted).unwrap().unwrap();
        assert_eq!(restored.model, "selected-model");
        assert!(restored.remembered);
        assert!(!serde_json::to_string(&restored)
            .unwrap()
            .contains("synthetic-key"));
        assert_eq!(
            restarted
                .lock()
                .unwrap()
                .connection
                .as_ref()
                .unwrap()
                .api_key,
            "synthetic-key"
        );
        disconnect(&restarted).unwrap();
        assert!(vault.read().unwrap().is_some());
        restore_connection(&vault, &restarted).unwrap();
        forget_saved_connection(&vault, &restarted).unwrap();
        assert!(vault.read().unwrap().is_none());
        assert!(restarted.lock().unwrap().connection.is_none());
    }
    #[test]
    fn secure_store_failures_and_invalid_saved_endpoints_fail_closed() {
        let vault = MemoryVault {
            fail_write: true,
            ..Default::default()
        };
        let connection = validate(c("openai", "https://api.openai.com/v1")).unwrap();
        assert!(save_connection(&vault, &connection, "model").is_err());
        assert!(vault.read().unwrap().is_none());
        let vault = MemoryVault {
            fail_delete: true,
            ..Default::default()
        };
        save_connection(&vault, &connection, "model").unwrap();
        let state = AiState::default();
        restore_connection(&vault, &state).unwrap();
        assert!(forget_saved_connection(&vault, &state).is_err());
        assert!(state.lock().unwrap().connection.is_some());
        assert!(vault.read().unwrap().is_some());
        let invalid = SavedConnection {
            version: 1,
            connection: c("openai", "https://example.invalid/v1"),
            model: "model".into(),
        };
        vault.write(&serde_json::to_vec(&invalid).unwrap()).unwrap();
        let clean = AiState::default();
        assert!(restore_connection(&vault, &clean).is_err());
        assert!(clean.lock().unwrap().connection.is_none());
        vault.write(b"invalid").unwrap();
        assert!(restore_connection(&vault, &clean).is_err());
    }
    #[test]
    fn remembered_connections_require_a_model_and_replace_the_previous_vault_item() {
        let vault = MemoryVault::default();
        let connection = validate(c("openai", "https://api.openai.com/v1")).unwrap();
        assert!(save_connection(&vault, &connection, "").is_err());
        save_connection(&vault, &connection, "first").unwrap();
        let second = validate(c("compatible", "http://localhost:11434/v1")).unwrap();
        save_connection(&vault, &second, "second").unwrap();
        let state = AiState::default();
        let restored = restore_connection(&vault, &state).unwrap().unwrap();
        assert_eq!(restored.provider, "compatible");
        assert_eq!(restored.endpoint, "http://localhost:11434/v1");
        assert_eq!(restored.model, "second");
    }
    fn c(provider: &str, endpoint: &str) -> Connection {
        Connection {
            provider: provider.into(),
            endpoint: endpoint.into(),
            api_key: "synthetic-key".into(),
            account_id: None,
        }
    }
    #[test]
    fn endpoints_are_explicit_and_credentials_cannot_redirect() {
        assert!(validate(c("openai", "https://api.openai.com/v1")).is_ok());
        assert!(validate(c("openai", "https://example.org/v1")).is_err());
        for endpoint in [
            "http://example.org/v1",
            "https://user:pass@example.org",
            "https://example.org?key=x",
            "https://example.org#x",
            "file:///tmp/x",
        ] {
            assert!(validate(c("compatible", endpoint)).is_err());
        }
        for endpoint in [
            "http://127.0.0.1:11434/v1",
            "http://localhost:1234/v1",
            "https://example.org/v1",
        ] {
            assert!(validate(c("compatible", endpoint)).is_ok());
        }
    }
    #[test]
    fn bodies_use_correct_protocol_without_tools() {
        let body = request_body("openai", "model", "system", "prompt");
        assert_eq!(body["store"], false);
        assert_eq!(body["input"], "prompt");
        assert!(body.get("tools").is_none());
        assert_eq!(
            request_body("anthropic", "m", "s", "p")["messages"][0]["content"],
            "p"
        );
        assert_eq!(
            request_body("gemini", "m", "s", "p")["contents"][0]["parts"][0]["text"],
            "p"
        );
        assert_eq!(request_body("compatible", "m", "s", "p")["stream"], false);
    }
}

#[cfg(test)]
mod transport_tests {
    use super::*;
    use std::io::{Read, Write};
    fn server(status: &str, body: &str) -> (String, std::thread::JoinHandle<String>) {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}/v1", listener.local_addr().unwrap());
        let reply=format!("HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",body.len());
        let handle = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            let mut bytes = Vec::new();
            let mut buf = [0; 8192];
            loop {
                let n = stream.read(&mut buf).unwrap();
                if n == 0 {
                    break;
                }
                bytes.extend_from_slice(&buf[..n]);
                if let Some(end) = bytes.windows(4).position(|s| s == b"\r\n\r\n") {
                    let header = String::from_utf8_lossy(&bytes[..end]).to_lowercase();
                    let len: usize = header
                        .lines()
                        .find_map(|l| l.strip_prefix("content-length: "))
                        .unwrap_or("0")
                        .parse()
                        .unwrap();
                    if bytes.len() >= end + 4 + len {
                        break;
                    }
                }
            }
            stream.write_all(reply.as_bytes()).unwrap();
            String::from_utf8(bytes).unwrap()
        });
        (url, handle)
    }
    #[tokio::test(flavor = "current_thread")]
    async fn model_discovery_uses_get_authentication_and_no_document_context() {
        let connection = |endpoint: &str| Connection {
            provider: "compatible".into(),
            endpoint: endpoint.into(),
            api_key: "synthetic-key".into(),
            account_id: None,
        };
        let (endpoint, thread) = server(
            "200 OK",
            r#"{"data":[{"id":"model-b"},{"id":"model-a"},{"id":"model-a"}]}"#,
        );
        let result = models::list(connection(&endpoint)).await.unwrap();
        assert_eq!(result.models.len(), 2);
        assert_eq!(result.models[0].id, "model-a");
        assert!(!result.truncated);
        let request = thread.join().unwrap();
        assert!(request.starts_with("GET /v1/models HTTP/1.1"));
        assert!(request
            .to_lowercase()
            .contains("authorization: bearer synthetic-key"));
        assert!(!request.contains("prompt"));
        let (endpoint, thread) = server(
            "401 Unauthorized",
            r#"{"error":"synthetic-key must not echo"}"#,
        );
        let error = models::list(connection(&endpoint)).await.err().unwrap();
        assert!(error.contains("denied"));
        assert!(!error.contains("synthetic-key"));
        thread.join().unwrap();
    }
    #[tokio::test(flavor = "current_thread")]
    async fn native_transport_posts_explicit_context_and_authorization() {
        let (endpoint, thread) = server(
            "200 OK",
            r#"{"choices":[{"finish_reason":"stop","message":{"content":"OK"}}]}"#,
        );
        let c = validate(Connection {
            provider: "compatible".into(),
            endpoint,
            api_key: "synthetic-key".into(),
            account_id: None,
        })
        .unwrap();
        let out = send(
            &c,
            "test-model",
            "test-system",
            "explicit synthetic context",
            &[],
        )
        .await
        .unwrap();
        assert_eq!(out["choices"][0]["message"]["content"], "OK");
        let raw = thread.join().unwrap();
        assert!(raw.starts_with("POST /v1/chat/completions HTTP/1.1"));
        assert!(raw
            .to_lowercase()
            .contains("authorization: bearer synthetic-key"));
        assert!(raw.contains("explicit synthetic context"));
    }
    #[tokio::test(flavor = "current_thread")]
    async fn provider_errors_do_not_echo_secrets_or_untrusted_bodies() {
        let (endpoint, thread) = server("401 Unauthorized", r#"{"error":"synthetic-secret echo"}"#);
        let c = Connection {
            provider: "compatible".into(),
            endpoint,
            api_key: "synthetic-key".into(),
            account_id: None,
        };
        let error = send(&c, "m", "s", "p", &[]).await.unwrap_err();
        assert!(error.contains("authentication"));
        assert!(!error.contains("synthetic"));
        thread.join().unwrap();
    }
}

// Public connection state only; credentials never leave this module.
pub fn active_provider(state: &AiState) -> Option<String> {
    state.lock().ok()?.connection.as_ref().map(|c|c.provider.clone())
}

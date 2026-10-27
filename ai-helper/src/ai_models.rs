// Adapted from PlasmidCraft (MIT); see licenses/PlasmidCraft-AI-MIT.txt.
//! Read-only provider model discovery. Never stores keys or submits document context.
use super::{validate, Connection};
use serde::Serialize;
use serde_json::Value;
use std::{collections::BTreeMap, collections::HashSet, time::Duration};
#[derive(Serialize)]
pub struct ModelInfo {
    pub id: String,
    pub name: String,
}
#[derive(Serialize)]
pub struct ModelList {
    pub models: Vec<ModelInfo>,
    pub truncated: bool,
}
fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 128
        && !id.contains("..")
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "-_.:/".contains(c))
}
fn page(provider: &str, value: &Value) -> Result<(Vec<ModelInfo>, Option<String>), String> {
    let rows = value[if provider == "gemini" { "models" } else { "data" }].as_array().ok_or("The provider returned an unsupported model-list format. You can enter a model ID manually.")?;
    let mut models = Vec::new();
    for row in rows {
        if provider == "gemini"
            && !row["supportedGenerationMethods"]
                .as_array()
                .is_some_and(|methods| {
                    methods
                        .iter()
                        .any(|m| m.as_str() == Some("generateContent"))
                })
        {
            continue;
        }
        let raw = row[if provider == "gemini" { "name" } else { "id" }]
            .as_str()
            .unwrap_or("");
        let id = if provider == "gemini" {
            raw.strip_prefix("models/").unwrap_or(raw)
        } else {
            raw
        };
        if !valid_id(id) || (provider == "gemini" && id.contains(['/', ':'])) {
            continue;
        }
        let name = row[if provider == "gemini" {
            "displayName"
        } else {
            "display_name"
        }]
        .as_str()
        .filter(|name| !name.chars().any(char::is_control))
        .unwrap_or(id)
        .chars()
        .take(256)
        .collect();
        models.push(ModelInfo {
            id: id.into(),
            name,
        });
    }
    let next = if provider == "gemini" {
        value["nextPageToken"].as_str()
    } else if value["has_more"].as_bool() == Some(true) {
        Some(
            value["last_id"]
                .as_str()
                .ok_or("The provider returned an invalid model-list cursor.")?,
        )
    } else {
        None
    };
    if next.is_some_and(|s| s.is_empty() || s.len() > 2048 || s.chars().any(char::is_control)) {
        return Err("The provider returned an invalid model-list cursor.".into());
    }
    Ok((models, next.map(str::to_string)))
}
pub async fn list(connection: Connection) -> Result<ModelList, String> {
    let c = validate(connection)?;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "Could not initialize model discovery.")?;
    let mut all = BTreeMap::new();
    let mut cursor: Option<String> = None;
    let mut seen = HashSet::new();
    for index in 0..10 {
        let mut url = reqwest::Url::parse(&format!("{}/models", c.endpoint))
            .map_err(|_| "Invalid model-list endpoint.")?;
        if c.provider == "anthropic" {
            url.query_pairs_mut().append_pair("limit", "1000");
        } else if c.provider == "gemini" {
            url.query_pairs_mut().append_pair("pageSize", "1000");
        }
        if let Some(cursor) = &cursor {
            let parameter = if c.provider == "anthropic" {
                "after_id"
            } else if c.provider == "gemini" {
                "pageToken"
            } else {
                "after"
            };
            url.query_pairs_mut().append_pair(parameter, cursor);
        }
        let mut request = client.get(url);
        match c.provider.as_str() {
            "anthropic" => {
                request = request
                    .header("x-api-key", &c.api_key)
                    .header("anthropic-version", "2023-06-01")
            }
            "gemini" => request = request.header("x-goog-api-key", &c.api_key),
            _ => {
                if !c.api_key.is_empty() {
                    request = request.bearer_auth(&c.api_key);
                }
            }
        }
        let mut response = request.send().await.map_err(|_| "Could not load models. Check your Internet connection and API endpoint, or enter a model ID manually.")?;
        if !response.status().is_success() {
            return Err(match response.status().as_u16() {
                401 | 403 => "Model discovery was denied. Check your API key and its model-list permissions; manual model entry is also available.".into(),
                429 => "Model discovery is rate limited. Retry later or enter a model ID manually.".into(),
                404 | 405 => "This endpoint does not provide a model list. Enter a model ID manually.".into(),
                n => format!("Model discovery returned HTTP {n}. Retry or enter a model ID manually."),
            });
        }
        let mut bytes = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|_| "Model discovery was interrupted.")?
        {
            if bytes.len() + chunk.len() > 1_000_000 {
                return Err("The model list exceeds the 1 MB page limit.".into());
            }
            bytes.extend_from_slice(&chunk);
        }
        let value: Value = serde_json::from_slice(&bytes)
            .map_err(|_| "The provider returned an invalid model list.")?;
        let (models, next) = page(&c.provider, &value)?;
        let mut overflow = false;
        for model in models {
            if all.contains_key(&model.id) {
                continue;
            }
            if all.len() >= 1000 {
                overflow = true;
                break;
            }
            all.insert(model.id.clone(), model);
        }
        if overflow || (next.is_some() && (all.len() >= 1000 || index == 9)) {
            return Ok(ModelList {
                models: all.into_values().collect(),
                truncated: true,
            });
        }
        let Some(next) = next else {
            return Ok(ModelList {
                models: all.into_values().collect(),
                truncated: false,
            });
        };
        if !seen.insert(next.clone()) {
            return Err(
                "The provider repeated a model-list cursor. Try manual model entry.".into(),
            );
        }
        cursor = Some(next);
    }
    unreachable!()
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn normalizes_provider_models_and_filters_unsupported_gemini_methods() {
        let (rows, cursor) = page("anthropic", &json!({"data":[{"id":"model-b","display_name":"Model B"},{"id":"../invalid"}],"has_more":true,"last_id":"model-b"})).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].name, "Model B");
        assert_eq!(cursor.as_deref(), Some("model-b"));
        let (rows, cursor) = page("gemini", &json!({"models":[{"name":"models/text-model","displayName":"Text","supportedGenerationMethods":["generateContent"]},{"name":"models/embedding","supportedGenerationMethods":["embedContent"]}],"nextPageToken":"opaque+/="})).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].id, "text-model");
        assert_eq!(cursor.as_deref(), Some("opaque+/="));
        let (rows, _) = page("openai", &json!({"data":[{"id":"model-a"}]})).unwrap();
        assert_eq!(rows[0].name, "model-a");
        assert!(page("compatible", &json!({"secret":"not a model list"})).is_err());
        assert!(page("anthropic", &json!({"data":[],"has_more":true})).is_err());
    }
}

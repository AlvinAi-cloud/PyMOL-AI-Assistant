//! Bounded app-produced images; never fetch URLs or read arbitrary files.
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};

#[derive(Clone)]
pub struct Image { pub url: String, pub mime: String, pub data: String }

pub fn parse(value: &Value) -> Result<Vec<Image>, String> {
    if value.is_null() { return Ok(vec![]); }
    let values = value.as_array().ok_or("Images must be an array.")?;
    if values.len() > 1 { return Err("Request one inspection image at a time.".into()); }
    values.iter().map(|v| {
        let url = v.as_str().ok_or("Invalid inspection image.")?;
        if url.len() > 1_000_100 { return Err("Inspection image exceeds the size limit.".into()); }
        let (mime, data) = if let Some(data) = url.strip_prefix("data:image/jpeg;base64,") {
            ("image/jpeg", data)
        } else if let Some(data) = url.strip_prefix("data:image/png;base64,") {
            ("image/png", data)
        } else { return Err("Inspection requires an embedded JPEG or PNG image.".into()); };
        let decoded = STANDARD.decode(data).map_err(|_| "Invalid image encoding.")?;
        if !(mime == "image/jpeg" && decoded.starts_with(&[255,216,255]) || mime == "image/png" && decoded.starts_with(b"\x89PNG\r\n\x1a\n")) {
            return Err("Invalid inspection image content.".into());
        }
        Ok(Image {url: url.into(), mime: mime.into(), data: data.into()})
    }).collect()
}

pub fn responses_input(prompt: &str, images: &[Image]) -> Value {
    let mut content = vec![json!({"type":"input_text", "text":prompt})];
    for image in images { content.push(json!({"type":"input_image", "image_url":image.url})); }
    json!([{"role":"user", "content":content}])
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn embedded_images_only() {
        assert!(parse(&json!(["https://example.com/private.png"])).is_err());
        assert!(parse(&json!(["data:image/jpeg;base64,bad"])).is_err());
        assert!(parse(&json!(["data:image/jpeg;base64,aGVsbG8="])).is_err());
        assert!(parse(&json!(["data:image/jpeg;base64,/9j/", "data:image/jpeg;base64,/9j/"])).is_err());
        assert_eq!(parse(&json!(["data:image/jpeg;base64,/9j/"])).unwrap().len(),1);
    }
}

//! Private stdin/stdout connection service. Never listens on a public socket.
#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]
mod ai;
mod images;
mod ai_vault;
mod chatgpt;
use serde_json::{json, Value};
use std::{io::{BufRead, Write}, path::PathBuf, sync::{Arc, Mutex}};
#[derive(Clone)]
pub struct Host { directory: PathBuf }
struct Service { host: Host, ai: ai::AiState, chatgpt: chatgpt::ChatGptState, model:Mutex<String> }
impl Service {
    fn selection(&self, provider: &str) -> Result<(), String> {
        use ai_vault::Vault;
        ai_vault::DeviceVault::new(self.host.directory.join("selection.json")).write(serde_json::to_string(&provider).unwrap().as_bytes())
    }
    async fn dispatch(&self, v: &Value) -> Result<Value, String> {
        let text = |name: &str| v[name].as_str().unwrap_or("").to_string();
        match text("action").as_str() {
            "status" => Ok(json!({"chatgpt":chatgpt::chatgpt_status(&self.chatgpt)?,"model":self.model.lock().map_err(|_|"Connection unavailable.")?.clone()})),
            "restore" => {
                use ai_vault::Vault;
                let mode = ai_vault::DeviceVault::new(self.host.directory.join("selection.json")).read()?.and_then(|b|serde_json::from_slice::<String>(&b).ok()).unwrap_or_default();
                if mode == "chatgpt" { Ok(json!({"chatgpt":chatgpt::chatgpt_restore(&self.chatgpt,&self.ai).await?,"model":self.model.lock().map_err(|_|"Connection unavailable.")?.clone()})) }
                else if mode == "api" { {
                    let mut connection=serde_json::to_value(ai::ai_restore_saved(self.host.clone(),&self.ai)?).unwrap();
                    let selected=self.model.lock().map_err(|_|"Connection unavailable.")?.clone();
                    if connection.is_object(){
                        if !selected.is_empty(){connection["model"]=json!(selected);}
                        *self.model.lock().map_err(|_|"Connection unavailable.")?=connection["model"].as_str().unwrap_or("").into();
                    }
                    Ok(json!({"connection":connection}))
                } }
                else { Ok(json!({})) }
            },
            "set_model" => {
                use ai_vault::Vault;
                let model=text("model");
                if model.is_empty() || model.len()>128 || model.contains("..") || !model.chars().all(|c|c.is_ascii_alphanumeric() || "-_.:/".contains(c)){return Err("Enter a valid model ID.".into());}
                ai_vault::DeviceVault::new(self.host.directory.join("model.json")).write(serde_json::to_string(&model).unwrap().as_bytes())?;
                *self.model.lock().map_err(|_|"Connection unavailable.")?=model.clone();
                Ok(json!({"model":model}))
            },
            "test" => {
                let response=ai::ai_request(text("model"),"Answer briefly. No study data is provided.".into(),"Reply: Connection successful.".into(),vec![],&self.ai,&self.chatgpt).await?;
                if response.is_null() || provider_error(&response) || matches!(response["status"].as_str(),Some("failed"|"incomplete")) || matches!(response["stop_reason"].as_str(),Some("max_tokens"|"refusal")){return Err("The provider did not complete the connection test.".into());}
                let content=response.to_string();
                if !content.contains("text") && !content.contains("content"){return Err("The provider returned no supported text response.".into());}
                Ok(json!({"notice":"Connection test completed. No study data was sent."}))
            },
            "cancel_login" => {chatgpt::chatgpt_cancel(&self.chatgpt)?;Ok(json!({}))},
            "connect" => {
                let c = serde_json::from_value(v["connection"].clone()).map_err(|_|"Invalid connection settings.")?;
                let remembered=v["remember"].as_bool().unwrap_or(true);
                let model=text("model");
                let result=ai::ai_connect(self.host.clone(),c,Some(remembered),Some(model.clone()),&self.ai)?;
                {
                    use ai_vault::Vault;
                    ai_vault::DeviceVault::new(self.host.directory.join("model.json")).write(serde_json::to_string(&model).unwrap().as_bytes())?;
                }
                *self.model.lock().map_err(|_|"Connection unavailable.")?=model;
                self.selection(if remembered {"api"} else {""})?;
                Ok(json!({"connection":result}))
            },
            "models" => {
                let c=if v["connection"].is_object(){Some(serde_json::from_value(v["connection"].clone()).map_err(|_|"Invalid connection settings.")?)}else{None};
                Ok(serde_json::to_value(ai::ai_list_models(c,&self.ai).await?).unwrap())
            },
            "sign_in" => {
                let id=v["registrationId"].as_str().filter(|s|!s.is_empty()).map(str::to_string);
                let result=chatgpt::chatgpt_sign_in(id,&self.chatgpt,&self.ai).await?;
                self.selection("chatgpt")?;
                Ok(json!({"chatgpt":result}))
            },
            "activate" => {
                let result=chatgpt::chatgpt_activate(text("registrationId"),&self.chatgpt,&self.ai).await?;
                self.selection("chatgpt")?;
                Ok(json!({"chatgpt":result}))
            },
            "account_models" => Ok(json!({"models":chatgpt::chatgpt_models(text("registrationId"),&self.chatgpt).await?})),
            "sign_out" => Ok(json!({"chatgpt":chatgpt::chatgpt_sign_out(text("registrationId"),&self.chatgpt,&self.ai).await?})),
            "disconnect" => {ai::ai_disconnect(&self.ai)?;Ok(json!({}))},
            "forget" => {ai::ai_forget_saved(self.host.clone(),&self.ai)?;if ai::active_provider(&self.ai).as_deref()!=Some("chatgpt"){self.selection("")?;}Ok(json!({}))},
            "request" => ai::ai_request(text("model"),text("system"),text("prompt"),images::parse(&v["images"])?,&self.ai,&self.chatgpt).await,
            "cancel" => {ai::ai_cancel(&self.ai)?;chatgpt::chatgpt_cancel(&self.chatgpt)?;Ok(json!({}))},
            _=>Err("Unknown AI connection operation.".into())
        }
    }
}
#[tokio::main]
async fn main() {
    let args:Vec<_>=std::env::args_os().collect();
    if args.len()!=3 || args[1]!="--profile" { return; }
    let directory=PathBuf::from(&args[2]);
    if !directory.is_absolute(){return;}
    use ai_vault::Vault;
    let model=ai_vault::DeviceVault::new(directory.join("model.json")).read().ok().flatten().and_then(|b|serde_json::from_slice::<String>(&b).ok()).unwrap_or_default();
    let service=Arc::new(Service {model:Mutex::new(model),host:Host {directory:directory.clone()},ai:ai::AiState::default(),chatgpt:chatgpt::ChatGptState::new(directory.join("chatgpt"))});
    let (tx,mut rx)=tokio::sync::mpsc::channel::<String>(8);
    std::thread::spawn(move || {
        let stdin=std::io::stdin();let mut reader=stdin.lock();
        loop {
            let mut bytes=Vec::new();
            use std::io::Read;
            match reader.by_ref().take(2_000_002).read_until(b'\n',&mut bytes) {
                Ok(0)|Err(_)=>break,
                Ok(_) if bytes.len()>2_000_000 || !bytes.ends_with(b"\n")=>break,
                Ok(_)=>if let Ok(line)=String::from_utf8(bytes){if tx.blocking_send(line).is_err(){break;}}else{break;}
            }
        }
    });
    let output=Arc::new(Mutex::new(std::io::stdout()));
    let permits=Arc::new(tokio::sync::Semaphore::new(8));
    while let Some(line)=rx.recv().await {
        let Ok(v)=serde_json::from_str::<Value>(&line) else { continue; };
        let Some(id)=v["id"].as_str().filter(|s|s.len()<=100).map(str::to_string) else {continue;};
        let service=service.clone();let output=output.clone();
        let permit=match permits.clone().try_acquire_owned(){Ok(p)=>p,Err(_)=>continue};
        tokio::spawn(async move {
            let result=service.dispatch(&v).await;
            let result=result.map(|mut value| {
                if value["chatgpt"].is_object() && ai::active_provider(&service.ai).as_deref()!=Some("chatgpt") {value["chatgpt"]["activeId"]=Value::Null;}
                value
            });
            let result=match result {Ok(value)=>json!({"id":id,"ok":true,"value":value}),Err(error)=>json!({"id":id,"ok":false,"error":error})};
            let mut encoded=result.to_string();
            if encoded.len()>1_400_000 {encoded=json!({"id":id,"ok":false,"error":"The provider response exceeded the size limit."}).to_string();}
            if let Ok(mut stream)=output.lock(){let _=writeln!(stream,"{encoded}");let _=stream.flush();}
            drop(permit);
        });
    }
    let _=service.dispatch(&json!({"action":"cancel"})).await;
    // Allow an already started rotating-token renewal to persist before exit.
    let _=tokio::time::timeout(std::time::Duration::from_secs(30),permits.acquire_many(8)).await;
}

// A successful Responses API object explicitly includes `error: null`.
fn provider_error(value:&Value)->bool {value.get("error").is_some_and(|error|!error.is_null())}
#[cfg(test)]
mod response_tests {
    use super::*;
    #[test]
    fn nullable_provider_errors_do_not_reject_success() {
        assert!(!provider_error(&json!({"status":"completed","error":null,"output":[]})));
        assert!(!provider_error(&json!({"choices":[]})));
        assert!(provider_error(&json!({"error":{"code":"synthetic-error"}})));
    }
}

use std::path::Path;

use serde_json::{json, Value};
use sqlx::SqlitePool;

use crate::db::{get_session, platform_check_url, session_dir};

pub(super) async fn session_payload_async(
    db: &SqlitePool,
    sessions_dir: &Path,
    session_id: &str,
    extra: Value,
) -> Result<Value, String> {
    let session = get_session(db, sessions_dir, session_id).await?;
    let check_url = platform_check_url(&session.platform)?;

    let mut payload = json!({
        "session_id": session.id,
        "platform": session.platform,
        "session_dir": session_dir(sessions_dir, session_id).to_string_lossy(),
        "check_url": check_url,
        "start_url": check_url,
    });

    if let Some(obj) = payload.as_object_mut() {
        if let Some(extra_obj) = extra.as_object() {
            for (key, value) in extra_obj {
                obj.insert(key.clone(), value.clone());
            }
        }
    }

    Ok(payload)
}

use std::path::{Path, PathBuf};

use chrono::Utc;
use sqlx::SqlitePool;
use uuid::Uuid;

use super::models::{SessionInfo, SessionRow};

pub fn now_iso() -> String {
    Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string()
}

pub fn session_dir(sessions_root: &Path, session_id: &str) -> PathBuf {
    sessions_root.join(session_id)
}

pub fn storage_state_path(sessions_root: &Path, session_id: &str) -> PathBuf {
    session_dir(sessions_root, session_id).join("storage_state.json")
}

pub fn has_storage(sessions_root: &Path, session_id: &str) -> bool {
    storage_state_path(sessions_root, session_id).is_file()
}

fn to_info(session: SessionRow, sessions_root: &Path) -> SessionInfo {
    let has_storage = has_storage(sessions_root, &session.id);
    session.into_info(has_storage)
}

pub async fn reset_running_on_startup(pool: &SqlitePool) -> Result<(), String> {
    let now = now_iso();
    sqlx::query(
        "UPDATE sessions SET status = 'idle', active_run_count = 0, updated_at = ? WHERE active_run_count > 0",
    )
    .bind(&now)
    .execute(pool)
    .await
    .map_err(|e| e.to_string())?;
    Ok(())
}

pub async fn list_sessions(
    pool: &SqlitePool,
    sessions_root: &Path,
    platform: &str,
) -> Result<Vec<SessionInfo>, String> {
    let rows = sqlx::query_as::<_, SessionRow>(
        "SELECT id, platform, name, status, active_run_count, last_checked_at, created_at, updated_at
         FROM sessions WHERE platform = ? ORDER BY name ASC",
    )
    .bind(platform)
    .fetch_all(pool)
    .await
    .map_err(|e| e.to_string())?;

    Ok(rows
        .into_iter()
        .map(|row| to_info(row, sessions_root))
        .collect())
}

pub async fn get_session(
    pool: &SqlitePool,
    sessions_root: &Path,
    session_id: &str,
) -> Result<SessionInfo, String> {
    let row = sqlx::query_as::<_, SessionRow>(
        "SELECT id, platform, name, status, active_run_count, last_checked_at, created_at, updated_at
         FROM sessions WHERE id = ?",
    )
    .bind(session_id)
    .fetch_one(pool)
    .await
    .map_err(|e| e.to_string())?;

    Ok(to_info(row, sessions_root))
}

pub async fn create_session(
    pool: &SqlitePool,
    sessions_root: &Path,
    platform: &str,
    name: &str,
) -> Result<SessionInfo, String> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err("session name is required".into());
    }

    let id = Uuid::new_v4().to_string();
    let dir = session_dir(sessions_root, &id);
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;

    let now = now_iso();
    let result = sqlx::query(
        "INSERT INTO sessions (id, platform, name, status, created_at, updated_at)
         VALUES (?, ?, ?, 'idle', ?, ?)",
    )
    .bind(&id)
    .bind(platform)
    .bind(trimmed)
    .bind(&now)
    .bind(&now)
    .execute(pool)
    .await;

    if let Err(e) = result {
        let message = e.to_string();
        if message.contains("UNIQUE") {
            return Err(format!(
                "a session named '{trimmed}' already exists for {platform}"
            ));
        }
        return Err(message);
    }

    get_session(pool, sessions_root, &id).await
}

pub async fn delete_session(
    pool: &SqlitePool,
    sessions_root: &Path,
    session_id: &str,
) -> Result<(), String> {
    let deleted = sqlx::query("DELETE FROM sessions WHERE id = ?")
        .bind(session_id)
        .execute(pool)
        .await
        .map_err(|e| e.to_string())?
        .rows_affected();

    if deleted == 0 {
        return Err(format!("session '{session_id}' not found"));
    }

    let dir = session_dir(sessions_root, session_id);
    if dir.exists() {
        std::fs::remove_dir_all(&dir).map_err(|e| e.to_string())?;
    }

    Ok(())
}

pub async fn mark_running(pool: &SqlitePool, session_id: &str) -> Result<(), String> {
    let now = now_iso();
    let updated = sqlx::query(
        "UPDATE sessions SET active_run_count = active_run_count + 1, status = 'running', updated_at = ? WHERE id = ?",
    )
    .bind(&now)
    .bind(session_id)
    .execute(pool)
    .await
    .map_err(|e| e.to_string())?
    .rows_affected();

    if updated == 0 {
        return Err(format!("session '{session_id}' not found"));
    }
    Ok(())
}

pub async fn mark_idle(pool: &SqlitePool, session_id: &str) -> Result<(), String> {
    let now = now_iso();
    sqlx::query(
        "UPDATE sessions SET
            active_run_count = CASE WHEN active_run_count > 0 THEN active_run_count - 1 ELSE 0 END,
            status = CASE WHEN active_run_count > 1 THEN 'running' ELSE 'idle' END,
            updated_at = ?
         WHERE id = ?",
    )
    .bind(&now)
    .bind(session_id)
    .execute(pool)
    .await
    .map_err(|e| e.to_string())?;
    Ok(())
}

pub async fn clear_active_runs(pool: &SqlitePool, session_id: &str) -> Result<(), String> {
    let now = now_iso();
    sqlx::query(
        "UPDATE sessions SET active_run_count = 0, status = 'idle', updated_at = ? WHERE id = ?",
    )
    .bind(&now)
    .bind(session_id)
    .execute(pool)
    .await
    .map_err(|e| e.to_string())?;
    Ok(())
}

pub async fn mark_checked(pool: &SqlitePool, session_id: &str) -> Result<(), String> {
    let now = now_iso();
    sqlx::query(
        "UPDATE sessions SET last_checked_at = ?, updated_at = ? WHERE id = ?",
    )
    .bind(&now)
    .bind(&now)
    .bind(session_id)
    .execute(pool)
    .await
    .map_err(|e| e.to_string())?;
    Ok(())
}

pub fn platform_check_url(platform: &str) -> Result<&'static str, String> {
    match platform {
        "linkedin" => Ok("https://www.linkedin.com/feed/"),
        "facebook" => Ok("https://www.facebook.com/"),
        "twitter" => Ok("https://x.com/home"),
        other => Err(format!("unsupported platform '{other}'")),
    }
}

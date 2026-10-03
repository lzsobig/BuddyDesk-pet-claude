use std::collections::VecDeque;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

const PROTOCOL_VERSION: u32 = 1;
const MAX_SNAPSHOT_BYTES: u64 = 64 * 1024;
const HEARTBEAT_TIMEOUT_MS: u64 = 6_000;
const REVEAL_WINDOW_MS: u64 = 5_000;
const MAX_SEEN_REVEAL_IDS: usize = 128;
const POLL_INTERVAL: Duration = Duration::from_millis(250);
const INPUT_SURFACE_ACTIVE_INTERVAL: Duration = Duration::from_millis(100);
const INPUT_SURFACE_IDLE_INTERVAL: Duration = Duration::from_secs(1);
const INPUT_SURFACE_ERROR_INTERVAL: Duration = Duration::from_secs(10);

#[derive(Clone, Copy, PartialEq, Eq)]
pub struct InputSurfaceRect {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

#[derive(Serialize)]
struct InputSurface<'a> {
    protocol_version: u32,
    pid: u32,
    updated_at_ms: u64,
    input_session: &'a str,
    active: bool,
    ready: bool,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    dpi: f64,
}

#[derive(Default)]
pub struct InputSurfacePublisher {
    path: Option<PathBuf>,
    last_publish: Option<Instant>,
    last_error_log: Option<Instant>,
    last_session: String,
    last_active: bool,
    last_ready: bool,
}

impl InputSurfacePublisher {
    pub fn new() -> Self {
        Self {
            path: dirs::home_dir().map(|home| {
                home.join(".buddydesk")
                    .join("winisland")
                    .join("input-surface.json")
            }),
            ..Self::default()
        }
    }

    pub fn publish(
        &mut self,
        now: Instant,
        input_session: &str,
        ready: bool,
        rect: InputSurfaceRect,
        dpi: f64,
    ) {
        let active = !input_session.is_empty();
        let interval = if active {
            INPUT_SURFACE_ACTIVE_INTERVAL
        } else {
            INPUT_SURFACE_IDLE_INTERVAL
        };
        if self.last_session == input_session
            && self.last_active == active
            && self.last_ready == ready
            && self
                .last_publish
                .is_some_and(|last| now.duration_since(last) < interval)
        {
            return;
        }
        self.last_publish = Some(now);
        self.last_session.clear();
        self.last_session.push_str(input_session);
        self.last_active = active;
        self.last_ready = ready;
        let Some(path) = self.path.as_ref() else {
            return;
        };
        let surface = InputSurface {
            protocol_version: 1,
            pid: std::process::id(),
            updated_at_ms: epoch_ms(),
            input_session,
            active,
            ready: active && ready,
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            dpi,
        };
        let result = (|| -> Result<(), String> {
            let directory = path.parent().ok_or("Input surface directory unavailable")?;
            fs::create_dir_all(directory).map_err(|error| error.to_string())?;
            let temp = directory.join(format!("input-surface-{}.tmp", std::process::id()));
            let bytes = serde_json::to_vec(&surface).map_err(|error| error.to_string())?;
            fs::write(&temp, bytes).map_err(|error| error.to_string())?;
            winisland_platform_windows::replace_file(&temp, path)
        })();
        if let Err(error) = result
            && self
                .last_error_log
                .is_none_or(|last| now.duration_since(last) >= INPUT_SURFACE_ERROR_INTERVAL)
        {
            log::warn!("Input surface publish failed: {error}");
            self.last_error_log = Some(now);
        }
    }
}

#[derive(Clone, Copy, Default, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AgentState {
    #[default]
    Idle,
    Listening,
    Transcribing,
    Understanding,
    Thinking,
    AskingConfirmation,
    Executing,
    Reminding,
    Success,
    Error,
}

#[derive(Clone, Copy, Default, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TaskStatus {
    #[default]
    Pending,
    Done,
}

#[derive(Clone, Default, Deserialize)]
#[serde(default)]
pub struct AgentTask {
    pub id: String,
    pub title: String,
    pub time_text: String,
    pub due_at: Option<String>,
    pub reminder_at: Option<String>,
    pub status: TaskStatus,
}

#[derive(Clone, Default, Deserialize)]
#[serde(default)]
pub struct AgentSnapshot {
    protocol_version: u32,
    pub revision: u64,
    updated_at_ms: u64,
    pub state: AgentState,
    pub label: String,
    pub tasks: Vec<AgentTask>,
    pub total_count: usize,
    pub completed_today: usize,
    pub next_reminder: String,
    pub reminder_id: String,
    pub reminder_task_id: Option<String>,
    pub reveal_id: String,
    pub reveal_at_ms: u64,
    pub input_session: String,
}

#[derive(Default)]
pub struct AgentBridge {
    path: Option<PathBuf>,
    snapshot: Option<AgentSnapshot>,
    connected: bool,
    next_poll: Option<Instant>,
    seen_reveal_ids: VecDeque<String>,
}

pub struct AgentPoll {
    pub changed: bool,
    pub new_reminder_id: Option<String>,
    pub reveal_requested: bool,
}

impl AgentSnapshot {
    pub fn state(&self, connected: bool) -> AgentState {
        if connected {
            self.state
        } else {
            AgentState::Idle
        }
    }

    pub fn reminder_active(&self, connected: bool) -> bool {
        connected && self.state == AgentState::Reminding && !self.reminder_id.is_empty()
    }

    pub fn visible_task_count(&self) -> usize {
        self.tasks.len().min(4)
    }

    pub fn additional_task_count(&self) -> usize {
        self.total_count
            .max(self.tasks.len())
            .saturating_sub(self.visible_task_count())
    }

    fn is_fresh(&self, now_ms: u64) -> bool {
        self.protocol_version == PROTOCOL_VERSION
            && self.updated_at_ms <= now_ms.saturating_add(1_000)
            && now_ms.saturating_sub(self.updated_at_ms) <= HEARTBEAT_TIMEOUT_MS
    }

    fn presentation_eq(&self, other: &Self) -> bool {
        self.revision == other.revision
            && self.state == other.state
            && self.label == other.label
            && self.total_count == other.total_count
            && self.completed_today == other.completed_today
            && self.next_reminder == other.next_reminder
            && self.reminder_id == other.reminder_id
            && self.reminder_task_id == other.reminder_task_id
            && self.reveal_id == other.reveal_id
            && self.reveal_at_ms == other.reveal_at_ms
            && self.input_session == other.input_session
            && self
                .tasks
                .iter()
                .map(task_key)
                .eq(other.tasks.iter().map(task_key))
    }
}

impl AgentBridge {
    pub fn new() -> Self {
        Self {
            path: dirs::home_dir()
                .map(|home| home.join(".buddydesk").join("winisland").join("agent.json")),
            ..Self::default()
        }
    }

    pub fn poll(&mut self, now: Instant) -> AgentPoll {
        if self.next_poll.is_some_and(|next| now < next) {
            return AgentPoll {
                changed: false,
                new_reminder_id: None,
                reveal_requested: false,
            };
        }
        self.next_poll = Some(now + POLL_INTERVAL);

        let now_ms = epoch_ms();
        let was_connected = self.connected;
        let previous = self.snapshot.clone();
        let mut accepted_snapshot = false;
        let previous_reminder = previous
            .as_ref()
            .filter(|snapshot| snapshot.reminder_active(was_connected))
            .map_or("", |snapshot| snapshot.reminder_id.as_str());
        if let Some(path) = &self.path
            && let Ok(snapshot) = read_snapshot(path)
            && snapshot.is_fresh(now_ms)
            && (previous.as_ref().is_none_or(|old| {
                snapshot.updated_at_ms > old.updated_at_ms
                    || (snapshot.updated_at_ms == old.updated_at_ms
                        && snapshot.revision >= old.revision)
            }))
        {
            self.snapshot = Some(snapshot);
            accepted_snapshot = true;
        }

        self.connected = self
            .snapshot
            .as_ref()
            .is_some_and(|snapshot| snapshot.is_fresh(now_ms));
        let new_snapshot = self.snapshot.as_ref();
        let changed = was_connected != self.connected
            || match (previous.as_ref(), new_snapshot) {
                (Some(before), Some(after)) => !before.presentation_eq(after),
                (None, Some(_)) => true,
                _ => false,
            };
        let new_reminder_id = new_snapshot
            .filter(|snapshot| {
                snapshot.reminder_active(self.connected)
                    && snapshot.reminder_id != previous_reminder
            })
            .map(|snapshot| snapshot.reminder_id.clone());
        let reveal_id = new_snapshot
            .filter(|snapshot| {
                accepted_snapshot
                    && self.connected
                    && !snapshot.reveal_id.is_empty()
                    && snapshot.reveal_at_ms <= now_ms
                    && now_ms - snapshot.reveal_at_ms <= REVEAL_WINDOW_MS
            })
            .map(|snapshot| snapshot.reveal_id.clone());
        let reveal_requested = reveal_id.is_some_and(|id| {
            if self.seen_reveal_ids.contains(&id) {
                false
            } else {
                self.seen_reveal_ids.push_back(id);
                if self.seen_reveal_ids.len() > MAX_SEEN_REVEAL_IDS {
                    self.seen_reveal_ids.pop_front();
                }
                true
            }
        });

        AgentPoll {
            changed,
            new_reminder_id,
            reveal_requested,
        }
    }

    pub fn snapshot(&self) -> Option<&AgentSnapshot> {
        self.snapshot.as_ref()
    }

    pub fn connected(&self) -> bool {
        self.connected
    }

    pub fn input_session(&self) -> &str {
        self.snapshot
            .as_ref()
            .filter(|_| self.connected)
            .map_or("", |snapshot| snapshot.input_session.as_str())
    }

    pub fn send_command(&self, action: &str, args: serde_json::Value) -> Result<(), String> {
        let path = self.path.as_ref().ok_or("Agent directory unavailable")?;
        let directory = path.parent().ok_or("Agent directory unavailable")?;
        write_agent_command(directory, action, args)
    }
}

pub(crate) fn send_settings_command(action: &str, args: serde_json::Value) -> Result<(), String> {
    let home = dirs::home_dir().ok_or("Agent directory unavailable")?;
    write_agent_command(&home.join(".buddydesk").join("winisland"), action, args)
}

fn write_agent_command(
    directory: &std::path::Path,
    action: &str,
    args: serde_json::Value,
) -> Result<(), String> {
    let commands = directory.join("agent-commands");
    fs::create_dir_all(&commands).map_err(|error| error.to_string())?;
    #[derive(Serialize)]
    struct Command<'a> {
        protocol_version: u32,
        id: String,
        issued_at_ms: u64,
        action: &'a str,
        #[serde(flatten)]
        args: serde_json::Value,
    }
    let command = Command {
        protocol_version: PROTOCOL_VERSION,
        id: format!("{}-{}", std::process::id(), epoch_nanos()),
        issued_at_ms: epoch_ms(),
        action,
        args,
    };
    let temp = commands.join(format!("{}.tmp", command.id));
    let mut file = File::create(&temp).map_err(|error| error.to_string())?;
    serde_json::to_writer(&mut file, &command).map_err(|error| error.to_string())?;
    file.flush().map_err(|error| error.to_string())?;
    drop(file);
    let target = commands.join(format!("{}.json", command.id));
    fs::rename(temp, target).map_err(|error| error.to_string())
}

fn read_snapshot(path: &PathBuf) -> Result<AgentSnapshot, String> {
    let file = File::open(path).map_err(|error| error.to_string())?;
    if file.metadata().map_err(|error| error.to_string())?.len() > MAX_SNAPSHOT_BYTES {
        return Err("Agent snapshot exceeds size limit".into());
    }
    let mut bytes = Vec::new();
    file.take(MAX_SNAPSHOT_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| error.to_string())?;
    if bytes.len() as u64 > MAX_SNAPSHOT_BYTES {
        return Err("Agent snapshot exceeds size limit".into());
    }
    let mut snapshot: AgentSnapshot =
        serde_json::from_slice(&bytes).map_err(|error| error.to_string())?;
    if snapshot.protocol_version != PROTOCOL_VERSION {
        return Err("Unsupported agent snapshot protocol".into());
    }
    snapshot.label = clean_text(&snapshot.label, 80);
    snapshot.next_reminder = clean_text(&snapshot.next_reminder, 120);
    snapshot.reminder_id = clean_text(&snapshot.reminder_id, 128);
    snapshot.reveal_id = clean_text(&snapshot.reveal_id, 128);
    snapshot.input_session = clean_text(&snapshot.input_session, 128);
    snapshot.reminder_task_id = snapshot
        .reminder_task_id
        .as_deref()
        .map(|id| clean_text(id, 128));
    snapshot.total_count = snapshot.total_count.min(100_000);
    snapshot.completed_today = snapshot.completed_today.min(100_000);
    snapshot.tasks.truncate(256);
    for task in &mut snapshot.tasks {
        task.id = clean_text(&task.id, 128);
        task.title = clean_text(&task.title, 200);
        task.time_text = clean_text(&task.time_text, 48);
        task.due_at = task.due_at.as_deref().map(|text| clean_text(text, 64));
        task.reminder_at = task.reminder_at.as_deref().map(|text| clean_text(text, 64));
    }
    Ok(snapshot)
}

fn task_key(task: &AgentTask) -> (&str, &str, &str, TaskStatus) {
    (&task.id, &task.title, &task.time_text, task.status)
}

fn clean_text(text: &str, limit: usize) -> String {
    text.chars()
        .filter(|character| !character.is_control())
        .take(limit)
        .collect()
}

fn epoch_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

fn epoch_nanos() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos()
}

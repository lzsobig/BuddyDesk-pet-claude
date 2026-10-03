use std::fs::{self, File};
use std::hash::{DefaultHasher, Hash, Hasher};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::process::{Child, Command};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

use crate::core::agent::AgentState;

const PROTOCOL_VERSION: u32 = 1;
const HEARTBEAT_TIMEOUT_MS: u64 = 6_000;
const MAX_MESSAGE_BYTES: u64 = 16_384;

#[derive(Clone, Copy, Default, PartialEq, Eq)]
pub enum PetMood {
    #[default]
    Idle,
    Happy,
    Sleep,
    Walk,
    Thinking,
    Error,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum CompanionAction {
    Chat,
    Settings,
    Pet,
    Sleep,
}

#[derive(Default, Deserialize)]
#[serde(default)]
struct BridgeState {
    protocol_version: u32,
    updated_at_ms: u64,
    state: String,
    preview: String,
    pet_name: String,
    backend: String,
    thinking_started_at_ms: u64,
}

#[derive(Clone, Deserialize, Hash)]
#[serde(default)]
struct PetPreferences {
    protocol_version: u32,
    pet_id: String,
    pet_name: String,
    island_enabled: bool,
    idle_path: String,
    thinking_path: String,
}

impl Default for PetPreferences {
    fn default() -> Self {
        Self {
            protocol_version: 1,
            pet_id: "orange".into(),
            pet_name: "小橘".into(),
            island_enabled: true,
            idle_path: String::new(),
            thinking_path: String::new(),
        }
    }
}

#[derive(Deserialize)]
struct Integration {
    protocol_version: u32,
    source_dir: PathBuf,
    python_path: PathBuf,
    #[serde(default)]
    assistant_executable: Option<PathBuf>,
}

#[derive(Serialize)]
struct BridgeCommand<'a> {
    protocol_version: u32,
    id: String,
    issued_at_ms: u64,
    action: &'a str,
}

pub struct Companion {
    directory: Option<PathBuf>,
    next_poll: Instant,
    child: Option<Child>,
    launching_since: Option<Instant>,
    startup_attempted: bool,
    connected: bool,
    agent_state: AgentState,
    agent_label: String,
    state: String,
    preview: String,
    pet_name: String,
    backend: String,
    error: Option<String>,
    sleeping: bool,
    happy_until: Option<Instant>,
    hover: Option<CompanionAction>,
    created: Instant,
    thinking_started_at_ms: u64,
    pet_preferences: PetPreferences,
    pet_modified: Option<SystemTime>,
}

impl Default for Companion {
    fn default() -> Self {
        let directory = dirs::home_dir().map(|home| home.join(".buddydesk").join("winisland"));
        let pet_preferences = directory
            .as_ref()
            .and_then(|directory| read_json::<PetPreferences>(&directory.join("pet.json")).ok())
            .filter(|preferences| preferences.protocol_version == 1)
            .unwrap_or_default();
        Self {
            directory,
            next_poll: Instant::now(),
            child: None,
            launching_since: None,
            startup_attempted: false,
            connected: false,
            agent_state: AgentState::Idle,
            agent_label: String::new(),
            state: String::new(),
            preview: String::new(),
            pet_name: "小橘".to_string(),
            backend: String::new(),
            error: None,
            sleeping: false,
            happy_until: None,
            hover: None,
            created: Instant::now(),
            thinking_started_at_ms: 0,
            pet_preferences,
            pet_modified: None,
        }
    }
}

impl Companion {
    pub fn set_agent_status(&mut self, state: AgentState, label: &str) {
        self.agent_state = state;
        self.agent_label = clean_text(label, 80);
    }

    pub fn poll(&mut self, now: Instant) -> bool {
        if now < self.next_poll {
            return false;
        }
        self.next_poll = now + Duration::from_millis(400);
        let before = self.presentation_key();
        if let Some(path) = self
            .directory
            .as_ref()
            .map(|directory| directory.join("pet.json"))
        {
            let modified = fs::metadata(&path)
                .and_then(|metadata| metadata.modified())
                .ok();
            if modified.is_some()
                && modified != self.pet_modified
                && let Ok(preferences) = read_json::<PetPreferences>(&path)
                && preferences.protocol_version == 1
            {
                self.pet_preferences = preferences;
                self.pet_modified = modified;
            }
        }
        if let Some(child) = self.child.as_mut() {
            match child.try_wait() {
                Ok(Some(status)) => {
                    if !status.success() {
                        self.error = Some("聊天助手未能启动，请检查 BuddyDesk 的运行环境".into());
                    }
                    self.child = None;
                    self.launching_since = None;
                }
                Err(error) => {
                    log::warn!("Cannot inspect companion process: {error}");
                    self.child = None;
                    self.launching_since = None;
                }
                Ok(None) => {}
            }
        }
        let snapshot = self
            .directory
            .as_ref()
            .and_then(|directory| read_json::<BridgeState>(&directory.join("state.json")).ok());
        self.connected = snapshot.as_ref().is_some_and(|state| {
            state.protocol_version == PROTOCOL_VERSION
                && epoch_ms().saturating_sub(state.updated_at_ms) <= HEARTBEAT_TIMEOUT_MS
                && state.updated_at_ms <= epoch_ms().saturating_add(1_000)
        });
        if self.connected {
            let snapshot = snapshot.unwrap_or_default();
            if snapshot.state == "thinking" {
                if snapshot.thinking_started_at_ms > 0 {
                    self.thinking_started_at_ms = snapshot.thinking_started_at_ms;
                } else if self.state != "thinking" || self.thinking_started_at_ms == 0 {
                    self.thinking_started_at_ms = epoch_ms();
                }
            } else {
                self.thinking_started_at_ms = 0;
            }
            self.state = snapshot.state;
            self.preview = clean_text(&snapshot.preview, 300);
            self.backend = clean_text(&snapshot.backend, 40);
            let name = clean_text(&snapshot.pet_name, 12);
            if !name.is_empty() {
                self.pet_name = name;
            }
            self.error = None;
            self.launching_since = None;
        }
        if !self.pet_preferences.pet_name.is_empty() {
            self.pet_name = clean_text(&self.pet_preferences.pet_name, 24);
        }
        if self
            .launching_since
            .is_some_and(|started| now.duration_since(started) > Duration::from_secs(45))
        {
            self.launching_since = None;
            self.error = Some("请在聊天助手的配置窗口中完成启动".into());
        }
        if self.happy_until.is_some_and(|until| now >= until) {
            self.happy_until = None;
        }
        if !self.startup_attempted && !self.connected {
            self.startup_attempted = true;
            if self.child.is_none()
                && let Err(error) = self.spawn_assistant(true)
                && !self.connected
            {
                self.error = Some(error);
            }
        }
        before != self.presentation_key()
    }

    fn presentation_key(&self) -> u64 {
        let mut hasher = DefaultHasher::new();
        self.pet_preferences.hash(&mut hasher);
        (
            self.connected,
            &self.state,
            &self.preview,
            &self.pet_name,
            &self.backend,
            self.error.as_deref(),
            self.launching_since.is_some(),
            self.happy_until.is_some(),
        )
            .hash(&mut hasher);
        hasher.finish()
    }

    pub fn connected(&self) -> bool {
        self.connected
    }

    pub fn name(&self) -> &str {
        &self.pet_name
    }

    pub fn status(&self) -> &str {
        if self.error.is_some() {
            "需要留意"
        } else if self.launching_since.is_some() {
            "正在打开"
        } else if self.agent_state != AgentState::Idle {
            if !self.agent_label.is_empty() {
                &self.agent_label
            } else {
                match self.agent_state {
                    AgentState::Listening => "正在聆听",
                    AgentState::Transcribing => "正在转写",
                    AgentState::Understanding => "正在理解",
                    AgentState::AskingConfirmation => "等待确认",
                    AgentState::Executing => "正在执行",
                    AgentState::Reminding => "事项提醒",
                    AgentState::Success => "已完成",
                    AgentState::Thinking => "思考中",
                    AgentState::Error => "遇到问题",
                    AgentState::Idle => "待命",
                }
            }
        } else if !self.connected {
            "待命"
        } else {
            match self.state.as_str() {
                "thinking" => "思考中",
                "result" => "已完成",
                "error" => "遇到问题",
                "notify" => "有新消息",
                _ => "已连接",
            }
        }
    }

    pub fn detail(&self) -> &str {
        if let Some(error) = &self.error {
            error
        } else if self.launching_since.is_some() {
            "正在准备聊天窗口…"
        } else if self.connected && !self.preview.is_empty() {
            &self.preview
        } else if self.connected {
            "问问题、写代码，或说说今天的想法。"
        } else {
            "点一下，打开你的 AI 聊天助手。"
        }
    }

    pub fn compact_status(&self) -> Option<&str> {
        if !self.island_enabled() {
            return None;
        }
        (self.error.is_some()
            || self.launching_since.is_some()
            || self.agent_state != AgentState::Idle
            || (self.connected && matches!(self.state.as_str(), "thinking" | "error" | "notify")))
        .then(|| self.status())
    }

    pub fn occupies_compact_center(&self, has_mini_content: bool, hidden: bool) -> bool {
        self.island_enabled() && !hidden && (!has_mini_content || self.compact_status().is_some())
    }

    pub fn island_enabled(&self) -> bool {
        self.pet_preferences.island_enabled
    }

    pub fn pet_id(&self) -> &str {
        &self.pet_preferences.pet_id
    }

    pub fn image_key(&self) -> String {
        format!(
            "{}|{}|{}",
            self.pet_id(),
            self.pet_preferences.idle_path,
            self.pet_preferences.thinking_path
        )
    }

    pub fn pet_image_bytes(&self, thinking: bool) -> Option<Vec<u8>> {
        if matches!(self.pet_id(), "orange" | "pixel-cat") {
            return None;
        }
        let directory = self
            .directory
            .as_ref()?
            .parent()?
            .join("pets")
            .canonicalize()
            .ok()?;
        let value = if thinking {
            &self.pet_preferences.thinking_path
        } else {
            &self.pet_preferences.idle_path
        };
        let path = PathBuf::from(value).canonicalize().ok()?;
        let extension = path.extension()?.to_str()?.to_ascii_lowercase();
        if !path.starts_with(directory)
            || !matches!(extension.as_str(), "png" | "webp" | "jpg" | "jpeg")
        {
            return None;
        }
        let file = File::open(path).ok()?;
        let limit = 16 * 1024 * 1024;
        if file.metadata().ok()?.len() > limit {
            return None;
        }
        let mut bytes = Vec::new();
        file.take(limit + 1).read_to_end(&mut bytes).ok()?;
        (bytes.len() as u64 <= limit).then_some(bytes)
    }

    pub fn mood(&self, playing: bool) -> PetMood {
        if matches!(
            self.agent_state,
            AgentState::Thinking
                | AgentState::Understanding
                | AgentState::Executing
                | AgentState::Transcribing
        ) || (self.connected && self.state == "thinking")
        {
            PetMood::Thinking
        } else if self.error.is_some() || (self.connected && self.state == "error") {
            PetMood::Error
        } else if self.happy_until.is_some() {
            PetMood::Happy
        } else if self.sleeping {
            PetMood::Sleep
        } else if playing {
            PetMood::Walk
        } else {
            PetMood::Idle
        }
    }

    pub fn elapsed(&self) -> f32 {
        self.created.elapsed().as_secs_f32()
    }

    pub fn thinking_seconds(&self) -> u64 {
        if self.thinking_started_at_ms == 0 {
            0
        } else {
            epoch_ms().saturating_sub(self.thinking_started_at_ms) / 1_000
        }
    }

    pub fn thinking_label(&self) -> &str {
        match self.preview.as_str() {
            "正在准备" | "正在思考" | "正在生成回答" | "正在使用工具" | "正在连接" => {
                &self.preview
            }
            _ => {
                if (self.thinking_seconds() / 5).is_multiple_of(2) {
                    "思考中"
                } else {
                    "正在琢磨"
                }
            }
        }
    }

    pub fn hovered(&self) -> Option<CompanionAction> {
        self.hover
    }

    pub fn set_hover(&mut self, hover: Option<CompanionAction>) -> bool {
        let changed = self.hover != hover;
        self.hover = hover;
        changed
    }

    pub fn act(&mut self, action: CompanionAction) {
        match action {
            CompanionAction::Pet => {
                self.sleeping = false;
                self.happy_until = Some(Instant::now() + Duration::from_secs(3));
            }
            CompanionAction::Sleep => {
                self.sleeping = !self.sleeping;
                self.happy_until = None;
            }
            CompanionAction::Chat | CompanionAction::Settings => {
                if let Err(error) = self.open_assistant(action) {
                    self.error = Some(error);
                    self.launching_since = None;
                }
            }
        }
    }

    fn open_assistant(&mut self, action: CompanionAction) -> Result<(), String> {
        let directory = self.directory.as_ref().ok_or("无法找到用户配置目录")?;
        fs::create_dir_all(directory).map_err(|_| "无法创建助手连接目录")?;
        let command = BridgeCommand {
            protocol_version: PROTOCOL_VERSION,
            id: format!("{}-{}", std::process::id(), epoch_nanos()),
            issued_at_ms: epoch_ms(),
            action: if action == CompanionAction::Settings {
                "open_settings"
            } else {
                "open_chat"
            },
        };
        let temp = directory.join(format!("commands-{}.tmp", std::process::id()));
        let mut file = File::create(&temp).map_err(|_| "无法发送助手指令")?;
        serde_json::to_writer(&mut file, &command).map_err(|_| "无法编码助手指令")?;
        file.flush().map_err(|_| "无法保存助手指令")?;
        drop(file);
        fs::rename(&temp, directory.join("commands.json")).map_err(|_| "无法更新助手指令")?;
        if self.connected || self.child.is_some() {
            return Ok(());
        }
        self.spawn_assistant(false)
    }

    fn spawn_assistant(&mut self, background: bool) -> Result<(), String> {
        let directory = self.directory.as_ref().ok_or("无法找到用户配置目录")?;
        let integration = read_json::<Integration>(&directory.join("integration.json")).ok();
        let packaged = std::env::current_exe().ok().and_then(|executable| {
            executable
                .parent()?
                .ancestors()
                .take(3)
                .map(|directory| directory.join("BuddyDesk.exe"))
                .find(|path| path.is_file())
        });
        let integrated = integration
            .as_ref()
            .filter(|integration| integration.protocol_version == PROTOCOL_VERSION)
            .and_then(|integration| integration.assistant_executable.as_ref())
            .filter(|path| path.is_absolute() && path.is_file());
        let mut process = if let Some(executable) = packaged.as_ref().or(integrated) {
            let mut process = Command::new(executable);
            process.arg("--island-running");
            if let Some(directory) = executable.parent() {
                process.current_dir(directory);
            }
            process
        } else {
            let (source, python) = match integration {
                Some(integration) if integration.protocol_version == PROTOCOL_VERSION => {
                    (integration.source_dir, integration.python_path)
                }
                _ => (
                    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                        .parent()
                        .ok_or("找不到聊天助手")?
                        .join("BuddyDesk-pet-claude-recovered"),
                    PathBuf::from("pythonw.exe"),
                ),
            };
            if !source.join("main.py").is_file() {
                return Err("先运行一次 BuddyDesk，连接后即可从这里打开聊天".into());
            }
            let mut process = Command::new(python);
            process.arg(source.join("main.py")).current_dir(source);
            process
        };
        process.arg("--winisland");
        if background {
            process.arg("--background");
        }
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            process.creation_flags(0x0800_0000);
        }
        self.child = Some(
            process
                .spawn()
                .map_err(|_| "聊天助手启动失败，请检查程序路径")?,
        );
        self.error = None;
        self.launching_since = (!background || !self.connected).then(Instant::now);
        Ok(())
    }
}

fn read_json<T: serde::de::DeserializeOwned>(path: &PathBuf) -> Result<T, String> {
    let file = File::open(path).map_err(|error| error.to_string())?;
    if file.metadata().map_err(|error| error.to_string())?.len() > MAX_MESSAGE_BYTES {
        return Err("Companion message exceeds size limit".into());
    }
    serde_json::from_reader(file.take(MAX_MESSAGE_BYTES)).map_err(|error| error.to_string())
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

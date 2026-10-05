from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from pet_library import codex_pets, import_codex_pet, import_animation_pack, import_pet, pets, resolve_pet, update_thinking_image
from theme import BG_SUBTLE, BORDER, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY


class PetSettings(QFrame):
    def __init__(self, settings, switch_type, combo_type=QComboBox, parent=None):
        super().__init__(parent)
        self._position = settings.get("pet_position")
        self._initial_id = str(settings.get("pet_id", "orange"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        self.selector = combo_type()
        self.selector.setIconSize(QSize(30, 30))
        self.selector.setAccessibleName("选择宠物")
        layout.addWidget(self.selector)
        previews = QHBoxLayout()
        self._previews = []
        for caption in ("日常", "思考"):
            column = QVBoxLayout()
            picture = QLabel()
            picture.setFixedHeight(82)
            picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
            picture.setStyleSheet(f"background:{BG_SUBTLE};border-radius:12px;")
            title = QLabel(caption)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
            column.addWidget(picture)
            column.addWidget(title)
            previews.addLayout(column)
            self._previews.append(picture)
        layout.addLayout(previews)
        buttons = QHBoxLayout()
        self.import_button = QPushButton("添加宠物…")
        self.animation_button = QPushButton("导入动作包…")
        self.thinking_button = QPushButton("设置思考图…")
        for button in (self.import_button, self.animation_button, self.thinking_button):
            button.setFixedHeight(30)
            button.setStyleSheet(f"QPushButton {{padding:0 9px;font-size:12px;border:1px solid {BORDER};border-radius:8px;color:{TEXT_SECONDARY};}}"
                                "QPushButton:disabled {color:#a9afb8;background:transparent;}")
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.codex_button = QPushButton("从本机 Codex 迁移宠物…")
        self.codex_button.setFixedHeight(28)
        self.codex_button.setStyleSheet(f"text-align:left;padding:0;border:none;background:transparent;color:{TEXT_SECONDARY};font-size:12px;")
        self.codex_button.clicked.connect(self._import_codex)
        layout.addWidget(self.codex_button)
        row = QHBoxLayout()
        label = QLabel("名称")
        label.setFixedWidth(54)
        label.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:12px;")
        self.name = QLineEdit(str(settings.get("pet_name", "小橘")))
        self.name.setMaxLength(24)
        row.addWidget(label)
        row.addWidget(self.name)
        layout.addLayout(row)
        self.desktop = switch_type("显示桌面宠物")
        self.desktop.setToolTip("独立显示在桌面，可拖动，双击打开聊天。")
        self.desktop.setChecked(bool(settings.get("pet_enabled", True)))
        self.island = switch_type("在灵动岛显示宠物")
        self.island.setToolTip("关闭后，灵动岛保留音乐和原有小组件；桌面宠物不受影响。")
        self.island.setChecked(bool(settings.get("pet_island_enabled", True)))
        self.roam = switch_type("允许桌面走动")
        self.roam.setChecked(bool(settings.get("pet_roam", False)))
        self.roam.setEnabled(self.desktop.isChecked())
        self.desktop.toggled.connect(self.roam.setEnabled)
        for switch in (self.desktop, self.island, self.roam):
            layout.addWidget(switch)
        reset = QPushButton("回到右下角")
        reset.setFixedHeight(28)
        reset.setStyleSheet(f"text-align:left;padding:0;border:none;background:transparent;color:{TEXT_SECONDARY};font-size:12px;")
        reset.clicked.connect(self._reset_position)
        layout.addWidget(reset)
        self._position_reset = False
        self.hint = QLabel("首次显示在右下角，拖动后记住位置。\n可导入透明 PNG / WebP，也支持 JPG；动作包使用 ZIP。保存后生效。")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
        layout.addWidget(self.hint)
        self._reload(self._initial_id)
        self.selector.currentIndexChanged.connect(self._selection_changed)
        self.import_button.clicked.connect(self._import)
        self.animation_button.clicked.connect(self._import_animation)
        self.thinking_button.clicked.connect(self._thinking)

    def _reload(self, selected):
        self.selector.blockSignals(True)
        self.selector.clear()
        for pet in pets():
            self.selector.addItem(QIcon(pet["idle"]), pet["name"] + " · " + pet["description"], pet["id"])
        index = self.selector.findData(selected)
        self.selector.setCurrentIndex(max(0, index))
        self.selector.blockSignals(False)
        self._refresh_preview()

    def _refresh_preview(self):
        pet = resolve_pet(self.selector.currentData())
        ratio = self.devicePixelRatioF()
        for label, kind in zip(self._previews, ("idle", "thinking")):
            pixmap = QPixmap(pet[kind]).scaled(round(78 * ratio), round(78 * ratio), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            pixmap.setDevicePixelRatio(ratio)
            label.setPixmap(pixmap)
        self.thinking_button.setEnabled(pet["custom"])
        if not self._position_reset:
            if pet.get("animated"):
                self.hint.setText(
                    f"{pet['animation_state_count']} 组动作 · {pet['animation_frame_count']} 帧\n"
                    "移过身体抚摸 · 按住拖动 · 双击聊天"
                )
            else:
                self.hint.setText("首次显示在右下角，拖动后记住位置。\n可导入透明 PNG / WebP，也支持 JPG；动作包使用 ZIP。保存后生效。")

    def _selection_changed(self):
        pet = resolve_pet(self.selector.currentData())
        self.name.setText(pet["name"])
        self._refresh_preview()

    def apply_external_setting(self, key, settings):
        if key == "pet_id":
            self._reload(settings.get("pet_id", "orange"))
            self.name.setText(str(settings.get("pet_name", "小橘")))
        elif key == "pet_name":
            self.name.setText(str(settings.get("pet_name", "小橘")))
        elif key == "pet_enabled":
            self.desktop.setChecked(bool(settings.get("pet_enabled", True)))
        elif key == "pet_island_enabled":
            self.island.setChecked(bool(settings.get("pet_island_enabled", True)))
        elif key == "pet_roam":
            self.roam.setChecked(bool(settings.get("pet_roam", False)))
        elif key == "pet_position":
            self._position = settings.get("pet_position")
            self._position_reset = self._position is None
            if self._position_reset:
                self.hint.setText("桌面宠物已回到主屏幕右下角。")

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_preview()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择宠物日常图片", "", "宠物图片 (*.png *.webp *.jpg *.jpeg)")
        if not path:
            return
        name, accepted = QInputDialog.getText(self, "添加宠物", "给宠物起个名字", text="我的宠物")
        if not accepted:
            return
        try:
            pet = import_pet(name, path)
            self._reload(pet["id"])
            self.name.setText(pet["name"])
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "无法添加宠物", str(error))

    def _thinking(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择思考姿态图片", "", "宠物图片 (*.png *.webp *.jpg *.jpeg)")
        if not path:
            return
        try:
            update_thinking_image(self.selector.currentData(), path)
            self._refresh_preview()
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "无法更新思考图", str(error))

    def _import_animation(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择宠物动作包", "", "宠物动作包 (*.zip)")
        if not path:
            return
        try:
            pet = import_animation_pack(path)
            self._position_reset = False
            self._reload(pet["id"])
            self.name.setText(pet["name"])
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "无法导入动作包", str(error))

    def _reset_position(self):
        self._position = None
        self._position_reset = True
        self.hint.setText("保存后，桌面宠物会回到主屏幕右下角。")

    def _import_codex(self):
        try:
            choices = codex_pets()
            if not choices:
                root = QFileDialog.getExistingDirectory(self, "选择 Codex 的 pets 目录")
                if not root:
                    return
                choices = codex_pets(root)
            if not choices:
                QMessageBox.information(self, "没有找到本地宠物", "请选择包含宠物子目录的 pets 文件夹。支持 pet.json 与标准 PNG / WebP spritesheet；云端角色需先下载到本机。")
                return
            dialog = QInputDialog(self)
            dialog.setWindowTitle("从 Codex 迁移宠物")
            dialog.setLabelText("选择要复制到 BuddyDesk 的角色。原文件不变；抚摸、拖动和睡眠缺少对应动作时沿用待机。")
            names = [f"{number + 1}. {pet['name']}" for number, pet in enumerate(choices)]
            dialog.setComboBoxItems(names)
            combo = dialog.findChild(QComboBox)
            if combo:
                import io
                from PIL import Image
                combo.setIconSize(QSize(42, 42))
                for number, pet in enumerate(choices):
                    with Image.open(pet["sheet"]) as sheet:
                        preview = sheet.crop((0, 0, 192, 208))
                        buffer = io.BytesIO()
                        preview.save(buffer, format="PNG")
                    pixmap = QPixmap()
                    pixmap.loadFromData(buffer.getvalue())
                    combo.setItemIcon(number, QIcon(pixmap))
                    from html import escape
                    combo.setItemData(number, escape(pet["description"]), Qt.ItemDataRole.ToolTipRole)
            dialog.setOkButtonText("迁移选中角色")
            dialog.setCancelButtonText("取消")
            if dialog.exec() != QInputDialog.DialogCode.Accepted:
                return
            selected = combo.currentIndex() if combo else names.index(dialog.textValue())
            pet = import_codex_pet(choices[selected]["folder"])
            self._reload(pet["id"])
            self.name.setText(pet["name"])
            self.hint.setText("已复制到 BuddyDesk，原 Codex 文件保持不变。点击保存后使用。")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "无法迁移宠物", str(error))

    def values(self):
        return {"pet_id": self.selector.currentData(), "pet_name": self.name.text().strip() or "我的宠物",
                "pet_enabled": self.desktop.isChecked(), "pet_island_enabled": self.island.isChecked(),
                "pet_roam": self.roam.isChecked(), "pet_position": self._position}

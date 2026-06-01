"""
Capture final_v2_pet_idle.png and final_v2_pet_happy.png.

Boots a minimal QApplication, instantiates PixelPet directly, and grabs
the QWidget via QScreen.grabWindow. Avoids the launcher flow.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Make project root importable
ROOT = r"C:\Users\李振\Desktop\hermes-pet-win - 副本"
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from ui.pixel_pet import PixelPet


def capture(state: str, out_path: str):
    app = QApplication.instance() or QApplication(sys.argv)
    pet = PixelPet(on_double_click=None)
    pet.pet_name = "小橘"
    pet.name_label.setText(pet.pet_name)
    pet.set_state(state)
    pet.show()
    # Force layout / paint
    app.processEvents()
    # Run animation for a few frames so sprite settles into a representative pose
    for _ in range(4):
        pet._animate()
        app.processEvents()
    # Set final state frame
    pet.set_state(state)
    for _ in range(2):
        pet._animate()
        app.processEvents()
    # Capture the widget region (pet + name label) with extra margin
    pix = pet.grab()
    pix.save(out_path, "PNG")
    print(f"saved: {out_path}  ({pix.width()}x{pix.height()})")
    pet.close()


if __name__ == "__main__":
    out_dir = ROOT
    capture("idle",  os.path.join(out_dir, "final_v2_pet_idle.png"))
    capture("happy", os.path.join(out_dir, "final_v2_pet_happy.png"))
    print("done")

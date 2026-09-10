import os
import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

# A QApplication must be instantiated to initialize default theme search paths properly
app = QApplication(sys.argv)

available_themes = []
for path in QIcon.themeSearchPaths():
  if os.path.isdir(path):
    for entry in os.listdir(path):
      theme_dir = os.path.join(path, entry)
      # A compliant theme must contain an index.theme file
      if os.path.isfile(os.path.join(theme_dir, 'index.theme')):
        if entry not in available_themes:
          available_themes.append(entry)

print('Available icon themes:', sorted(available_themes))

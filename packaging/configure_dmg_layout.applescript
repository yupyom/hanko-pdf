tell application "Finder"
  tell disk "Hanko PDF"
    open
    delay 1
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set bounds of container window to {120, 120, 800, 570}

    set viewOptions to icon view options of container window
    set arrangement of viewOptions to not arranged
    set icon size of viewOptions to 128
    set text size of viewOptions to 14

    set position of item "Hanko PDF.app" to {175, 230}
    set position of item "Applications" to {495, 230}
    update without registering applications
  end tell
end tell

# What's new

## Version 1.0.0

First public release of **Wallpaper Studio**.

### Wallpapers

- Still images: JPG, PNG, BMP, WEBP, TIFF, ICO.
- Animated images: GIF, APNG, animated WEBP.
- Video: MP4, MKV, WEBM, MOV, AVI, WMV and many more, through libVLC.
- Web wallpapers in HTML, CSS and JavaScript, run inside a sandbox.
- Five fit modes: fill, fit, stretch, centre, tile.

### The wallpaper sits behind your icons

On Windows 11 24H2 and later the usual technique stops working: the wallpaper
either never appears, or it covers the desktop icons. Wallpaper Studio works
around this and draws the wallpaper **behind your icons**, video included. Run
`--diagnostic` at any time to confirm it on your machine.

### Scheduling

- As many rules as you like, per display or for every display.
- Night ranges that cross midnight are handled correctly.
- Pick the days of the week, and priorities when ranges overlap.
- A change missed while the computer slept is applied on wake-up.
- A two-click assistant creates a day / night schedule for you.

### Multiple displays

- Each display keeps its own settings, even after being unplugged.
- A different wallpaper per display, the same one everywhere, or one
  panoramic image spread across them.

### Library and editing

- Import single files, whole folders, or drag and drop.
- Tags, collections, favourites, search and filters.
- Editor: brightness, contrast, saturation, hue, blur, rotation, mirrors.
- Eight particle effects: rain, snow, stars, fog, glows, waves and more.
- Media conversion: video to GIF, frame extraction, re-encoding.

### Light on resources

Built for a modest computer:

- **7 MB** of memory once the window is closed, down from 144 MB.
- **0 %** CPU in the background.
- The interface is only built when opened, and freed when closed.
- The video player is unloaded as soon as no video is on screen.
- Automatic pause: fullscreen games, battery power, locked session.

### Also

- Interface in French and English, chosen on first launch.
- Runs in the background from the notification area.
- Starts with Windows, without administrator rights.
- Checks for updates, downloads and installs them on request.

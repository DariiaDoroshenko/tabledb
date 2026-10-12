Скріншоти GUI для звіту (Linux, без монітора)
=============================================
Потрібно: xvfb, ImageMagick (команди import, convert), Python з tkinter.

Звичайний запуск:
    xvfb-run -a -s "-screen 0 1280x800x24" python tools/make_screenshots.py screenshots

Якщо Tk зібрано без Xft (на знімках зникають літери і, є, ь), підключіть
TrueType-шрифт як X-шрифт: покладіть DejaVuSans.ttf та DejaVuSans-Bold.ttf у теку,
створіть у ній fonts.scale (і копію fonts.dir) з рядками
    DejaVuSans.ttf -dejavu-DejaVu Sans-medium-r-normal--0-0-0-0-p-0-iso10646-1
    DejaVuSans-Bold.ttf -dejavu-DejaVu Sans-bold-r-normal--0-0-0-0-p-0-iso10646-1
(перший рядок файлу — кількість шрифтів, тут 2) і додайте  -fp <тека>,built-ins  до опцій Xvfb.
На Windows і в звичайному Linux-середовищі з Xft це не потрібно.

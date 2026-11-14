# Sonopipe 🔊📱

> **Кроссплатформенная передача системного звука с компьютера (Linux / Windows) на Android-смартфон через ADB (USB) с ультранизкой задержкой.**

Используйте ваш Android-смартфон в качестве внешнего проводного динамика для ПК без root-прав, помех Wi-Fi и задержек Bluetooth.

---

## ⚡ Быстрая установка в одну команду (Linux)

Установите Sonopipe одной строкой. Скрипт автоматически скачает программу, настроит виртуальное окружение Python со всеми зависимостями и добавит глобальную команду и alias **`sonopipe`** в ваш шелл (`~/.bashrc`, `~/.zshrc`, `fish`):

```bash
curl -fsSL https://raw.githubusercontent.com/sshremoteh/sonopipe/main/install.sh | bash
```

*(или через `wget`:)*
```bash
wget -qO- https://raw.githubusercontent.com/sshremoteh/sonopipe/main/install.sh | bash
```

После завершения просто перезапустите терминал (или выполните `source ~/.bashrc` / `source ~/.zshrc`) и введите:
```bash
sonopipe
```

---

## 🚀 Особенности

- **Ультранизкая задержка (<25 мс)**: передача сырого PCM-потока (16-bit, 48000 Гц / 44100 Гц, стерео) блоками по 10–20 мс через USB с флагом `TCP_NODELAY`.
- **AudioTrack Fast Track**: на Android задействован нативный `AudioTrack` с аппаратным флагом низкой задержки (`FLAG_LOW_LATENCY` / `PERFORMANCE_MODE_LOW_LATENCY`).
- **Без root-прав**: работает на любых стандартных смартфонах с Android 7.0+.
- **Кроссплатформенность**:
  - **Linux**: захват системного звука через PipeWire / PulseAudio монитор-потоки.
  - **Windows**: прямой захват через WASAPI Loopback.
- **Два режима работы**:
  - **GUI** (PySide6): современный темный интерфейс, живой VU-метр громкости, автоопределение ADB-устройств, мониторинг скорости и переключатели качества.
  - **CLI**: запуск без графической оболочки (идеально для скриптов, автозапуска и серверов).
- **Установка APK прямо из GUI**: кнопка **«📱 Install APK to Phone»** установит мобильное приложение на подключенный телефон в один клик.

---

## 📱 Быстрый старт

### 1. Подключение смартфона
1. Подключите телефон к компьютеру через USB-кабель.
2. Включите **«Отладку по USB»** (USB Debugging) в меню «Для разработчиков» на телефоне.

### 2. Установка приложения на телефон
- **Через GUI**: запустите `sonopipe` и нажмите кнопку **`📱 Install APK to Phone`**.
- **Через терминал**:
  ```bash
  sonopipe --install-apk
  ```
- **Вручную через ADB**:
  ```bash
  adb install -r apk/app-debug.apk
  ```

На телефоне откроется приложение **Sonopipe**. Нажмите кнопку **Start Receiver** (индикатор загорится желтым: *«Listening on port 12850»*).

### 3. Запуск трансляции звука

#### Графический интерфейс:
```bash
sonopipe
```
В окне программы нажмите **Start Streaming**. Порт пробросится автоматически, и звук с ПК сразу пойдет через телефон.

#### Режим командной строки (CLI):
```bash
# Стандартный запуск
sonopipe --cli

# Просмотр доступных аудиоустройств захвата
sonopipe --list-audio-devices

# Просмотр подключенных устройств ADB
sonopipe --list-adb-devices

# Выбор конкретного устройства, громкости (120%) и порта
sonopipe --cli -d <SERIAL> -p 12850 -v 1.2
```

Остановка стриминга в CLI: `Ctrl + C`.

---

## 🛠 Ручная установка и сборка из исходников

Если вы хотите развернуть проект вручную:

```bash
git clone https://github.com/sshremoteh/sonopipe.git
cd sonopipe

# Создание виртуального окружения
python3 -m venv .venv
source .venv/bin/activate  # На Windows: .venv\Scripts\activate

# Установка зависимостей
pip install -r requirements.txt

# Установка пакета локально
pip install -e .
```

Запуск:
```bash
python3 run.py
```

### Сборка Android APK:
```bash
cd android
./gradlew assembleDebug
# Готовый файл: android/app/build/outputs/apk/debug/app-debug.apk
```

---

## 🏛 Архитектура проекта

```
sonopipe/
├── sonopipe/                     # Исходный код Python для ПК
│   ├── adb/                      # Модуль взаимодействия с ADB
│   │   ├── manager.py            # Поиск устройств, port forwarding, am start
│   │   └── installer.py          # Автоматическая сборка и установка APK
│   ├── capture/                  # Модульная система захвата звука
│   │   ├── base.py               # Базовый интерфейс AudioCaptureBase
│   │   ├── factory.py            # Автовыбор бэкенда для текущей ОС
│   │   ├── linux_pulse.py        # Захват PipeWire / PulseAudio (parec / monitor sink)
│   │   ├── windows_wasapi.py     # Захват WASAPI Loopback (Windows)
│   │   └── soundcard_backend.py  # Кроссплатформенный бэкенд на soundcard
│   ├── gui/                      # Графический интерфейс на PySide6
│   │   └── main_window.py        # Тёмный интерфейс, VU-метр, кнопка установки APK
│   ├── stream/                   # Сетевой транспорт и протокол
│   │   ├── protocol.py           # 16-байтный бинарный заголовок
│   │   └── sender.py             # TCP-клиент, регулятор громкости, статистика
│   ├── cli.py                    # Режим работы через терминал
│   └── main.py                   # Точка входа программы
├── android/                      # Android-приложение (Kotlin)
│   ├── app/src/main/java/com/adbsound/app/
│   │   ├── MainActivity.kt         # UI управления и индикации
│   │   ├── AudioReceiverService.kt # Foreground-сервис со ServerSocket
│   │   ├── AudioTrackPlayer.kt     # Низколатентный AudioTrack
│   │   └── AdbProtocol.kt          # Парсер протокола
│   └── build.gradle.kts
├── apk/                          # Предсобранный готовый APK (v1.0.0)
│   └── app-debug.apk
├── install.sh                    # Скрипт автоустановки и создания alias
├── requirements.txt
├── setup.py
└── run.py
```

---

## ❓ Решение проблем

| Проблема | Причина | Решение |
| :--- | :--- | :--- |
| `Connection refused at 127.0.0.1:12850` | На телефоне не нажат «Start Receiver» или не настроен форвардинг | Нажмите **Start Receiver** на телефоне и запустите стриминг повторно |
| `adb: command not found` | Не установлены утилиты Android platform-tools | `sudo pacman -S android-tools` (Arch) или `sudo apt install adb` (Ubuntu) |
| Нет звука | Громкость заглушена в микшере | Проверьте уровень громкости на телефоне и ползунок громкости в окне Sonopipe |
| Рассинхронизация звука | Большой аудиобуфер драйвера | Запустите с меньшим размером чанка: `sonopipe --cli --chunk-size 480` (~10 мс) |

---

## 📄 Лицензия

MIT License © 2026. Свободно для использования и модификации.

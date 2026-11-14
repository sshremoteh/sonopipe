# Sonopipe 🔊📱

> **Кроссплатформенная передача системного звука с компьютера (Linux / Windows) на Android-смартфон через ADB (USB и Wi-Fi) с ультранизкой задержкой.**

Используйте ваш Android-смартфон в качестве внешнего проводного или беспроводного динамика для ПК без root-прав, помех и задержек Bluetooth.

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

- **Два режима подключения**:
  - 🔌 **USB-кабель**: максимальная стабильность и минимальная задержка (<20 мс).
  - 📶 **Wireless ADB (Wi-Fi)**: передача аудио по локальной беспроводной сети без проводов с поддержкой сопряжения Android 11+!
- **AudioTrack Fast Track**: на Android задействован нативный `AudioTrack` с аппаратным флагом низкой задержки (`FLAG_LOW_LATENCY` / `PERFORMANCE_MODE_LOW_LATENCY`).
- **Без root-прав**: работает на любых стандартных смартфонах с Android 7.0+.
- **Кроссплатформенность**:
  - **Linux**: захват системного звука через PipeWire / PulseAudio монитор-потоки.
  - **Windows**: прямой захват через WASAPI Loopback.
- **Интерфейс Material Design 3 (MD3)**:
  - Тёмная тема с адаптивным слоем `QScrollArea` (никаких обрезанных элементов на любых экранах и тайлинговых WM).
  - Анимированный пульсирующий индикатор стрима (`AnimatedStatusBadge`).
  - Профессиональный двухканальный стерео VU-метр (L / R) с dB-шкалой и гравитационным затуханием пиков.
  - Сегментированные пресеты задержки: `10ms`, `20ms`, `40ms`.
  - Кнопка установки APK на телефон в один клик.

---

## 📶 Подключение через Wireless ADB (Wi-Fi)

Sonopipe поддерживает работу полностью по воздуху через Wi-Fi!

### Способ 1: Автоматический переход в 1 клик через USB (Рекомендуемый)
1. Подключите телефон к компьютеру по USB-кабелю один раз (с включенной отладкой по USB).
2. Убедитесь, что телефон и ПК подключены к одной Wi-Fi сети.
3. В окне Sonopipe перейдите на вкладку **«📶 Wireless ADB»** и нажмите **`⚡ Switch to Wi-Fi via USB`**.
4. Программа сама определит Wi-Fi IP телефона, активирует порт `5555` и подключится по воздуху.
5. **Отключите USB-кабель!** Смартфон останется подключенным по беспроводной сети.

### Способ 2: Android 11+ Беспроводная отладка (Полностью без кабеля)
1. На телефоне: *Настройки → Параметры разработчика → Беспроводная отладка* (Wireless debugging). Включите тумблер.
2. Нажмите *«Подключить с помощью кода сопряжения»* (Pair device with pairing code). Вы увидите:
   - IP-адрес и порт сопряжения (например, `192.168.1.45:37125`)
   - 6-значный код сопряжения (например, `842109`)
3. В Sonopipe нажмите **`🔑 Pair (Android 11+)`**, введите эти данные и нажмите **Pair Device**.
4. После успешного сопряжения введите в поле *Phone Wi-Fi IP* основной адрес и порт из настроек беспроводной отладки и нажмите **Connect Wi-Fi**.

### Способ 3: Через терминал (CLI)
```bash
# Перевести подключенный по USB телефон в режим TCP/IP:
sonopipe --enable-tcpip 5555

# Подключиться к телефону по его Wi-Fi IP:
sonopipe --connect-wireless 192.168.1.45:5555

# Открыть интерактивную инструкцию в терминале:
sonopipe --wireless-guide
```

---

## 📱 Быстрый старт (USB)

### 1. Подключение смартфона
1. Подключите телефон к компьютеру через USB-кабель.
2. Включите **«Отладку по USB»** (USB Debugging) в меню «Для разработчиков» на телефоне.

### 2. Установка приложения на телефон
- **Через GUI**: запустите `sonopipe` и нажмите кнопку **`📲 Install & Launch APK on Phone`**.
- **Через терминал**:
  ```bash
  sonopipe --install-apk
  ```
- **Вручную через ADB**:
  ```bash
  adb install -r apk/app-debug.apk
  ```

На телефоне откроется приложение **Sonopipe** (на экране сразу отобразится текущий Wi-Fi IP устройства). Нажмите кнопку **Start Receiver** (индикатор загорится: *«Listening on port 12850»*).

### 3. Запуск трансляции звука

#### Графический интерфейс:
```bash
sonopipe
```
В окне программы выберите телефон в списке устройств и нажмите **Start Streaming**. Порт пробросится автоматически, и звук с ПК сразу пойдет через телефон.

#### Режим командной строки (CLI):
```bash
# Стандартный запуск
sonopipe --cli

# Просмотр доступных аудиоустройств захвата
sonopipe --list-audio-devices

# Просмотр подключенных устройств ADB (включая Wi-Fi)
sonopipe --list-adb-devices

# Выбор конкретного устройства, громкости (120%) и порта
sonopipe --cli -d 192.168.1.45:5555 -p 12850 -v 1.2
```

Остановка стриминга в CLI: `Ctrl + C`.

---

## 🛠 Ручная установка и сборка из исходников

```bash
git clone https://github.com/sshremoteh/sonopipe.git
cd sonopipe

python3 -m venv .venv
source .venv/bin/activate  # На Windows: .venv\Scripts\activate

pip install -r requirements.txt
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
# Готовый файл: apk/app-debug.apk
```

---

## 🏛 Архитектура проекта

```
sonopipe/
├── sonopipe/                     # Исходный код Python для ПК
│   ├── adb/                      # Модуль взаимодействия с ADB
│   │   ├── manager.py            # Поиск устройств, Wi-Fi connect/pair/tcpip, port forwarding
│   │   └── installer.py          # Автоматическая сборка и установка APK
│   ├── capture/                  # Модульная система захвата звука
│   │   ├── base.py               # Базовый интерфейс AudioCaptureBase
│   │   ├── factory.py            # Автовыбор бэкенда для текущей ОС
│   │   ├── linux_pulse.py        # Захват PipeWire / PulseAudio (parec / monitor sink)
│   │   └── windows_wasapi.py     # Захват WASAPI Loopback (Windows)
│   ├── gui/                      # MD3 Графический интерфейс (PySide6)
│   │   └── main_window.py        # USB/Wi-Fi панель, стерео VU-метр, диалоги сопряжения
│   ├── stream/                   # Сетевой транспорт и протокол
│   │   ├── protocol.py           # 16-байтный бинарный заголовок
│   │   └── sender.py             # TCP-клиент, регулятор громкости, стереометрия
│   ├── cli.py                    # Режим работы через терминал с командами Wi-Fi
│   └── main.py                   # Точка входа программы
├── android/                      # Android-приложение (Kotlin)
│   ├── app/src/main/java/com/adbsound/app/
│   │   ├── MainActivity.kt         # UI управления, вывод Wi-Fi IP адреса
│   │   ├── AudioReceiverService.kt # Foreground-сервис со ServerSocket
│   │   ├── AudioTrackPlayer.kt     # Низколатентный AudioTrack
│   │   └── AdbProtocol.kt          # Парсер протокола
│   └── build.gradle.kts
├── apk/                          # Предсобранный готовый APK (v1.2.0)
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
| `failed to connect to IP:5555` | Порт 5555 не открыт на телефоне или устройство не в одной сети Wi-Fi | Проверьте подключение к общему Wi-Fi и выполните `⚡ Switch to Wi-Fi via USB` при подключенном кабеле |
| `adb: command not found` | Не установлены утилиты Android platform-tools | `sudo pacman -S android-tools` (Arch) или `sudo apt install adb` (Ubuntu) |
| Задержка звука по Wi-Fi | Нагруженная сеть Wi-Fi | Переключитесь на 5 ГГц Wi-Fi или используйте пресет `⚡ Low (10ms)` / проводной USB-режим |

---

## 📄 Лицензия

MIT License © 2026. Свободно для использования и модификации.

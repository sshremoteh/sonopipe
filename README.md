# Sonopipe 🔊📱🎙

> **Кроссплатформенная передача звука и микрофона между компьютером (Linux / Windows) и Android-смартфоном через ADB (USB и Wi-Fi) с ультранизкой задержкой.**

Превратите ваш Android-смартфон в качественный динамик, внешний беспроводной микрофон или полноценную гарнитуру для ПК без root-прав, помех и задержек Bluetooth.

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

- **3 Режима работы**:
  - 🔊 **Speaker Only (PC → Phone)**: вывод звука с компьютера на динамики или наушники телефона.
  - 🎙 **Microphone Only (Phone → PC)**: использование телефона как микрофона для ПК (Discord, Telegram, OBS, Zoom, CS2 и т.д.).
  - 🎧 **Full Duplex (PC ⇄ Phone)**: одновременный двухсторонний звук (гарнитура) с аппаратным шумоподавлением и эхоподавлением (AEC + NS).
- **Два типа подключения**:
  - 🔌 **USB-кабель**: максимальная стабильность и минимальная задержка (<15-20 мс).
  - 📶 **Wireless ADB (Wi-Fi)**: передача аудио по локальной беспроводной сети без проводов с поддержкой сопряжения Android 11+ и **QR-кодов**!
- **Виртуальный микрофон на ПК**:
  - **Linux (PipeWire / PulseAudio)**: автоматическое создание виртуального микрофона (`Sonopipe Virtual Microphone`). Любая программа на ПК видит телефон как физический микрофонный вход.
  - **Windows**: маршрутизация потока через виртуальные аудиокабели (VB-CABLE / Virtual Audio Cable).
- **AudioTrack Fast Track & VOICE_COMMUNICATION**:
  - Воспроизведение на Android через нативный `AudioTrack` с аппаратным флагом низкой задержки (`PERFORMANCE_MODE_LOW_LATENCY`).
  - Захват микрофона через источник `VOICE_COMMUNICATION` с активацией аппаратных алгоритмов `AcousticEchoCanceler` и `NoiseSuppressor`.
- **Без root-прав**: работает на любых стандартных смартфонах с Android 7.0+.
- **Интерфейс Material Design 3 (MD3) (v1.5.0)**:
  - Тональная тёмная тема MD3, аккуратные карточки, сегментированный переключатель режимов (`Speaker` / `Microphone` / `Headset`) и выпадающее MD3-меню **`⋮`**.
  - **Запоминание Wi-Fi устройств и автопереподключение**: программа автоматически запоминает подключённые по Wi-Fi смартфоны, показывает чипы быстрого подключения в 1 клик на главном экране и умеет переподключаться в фоне при запуске.
  - **Менеджер Wi-Fi устройств (`📶 Wi-Fi`)**: неблокирующий поиск по mDNS (`⚡ Auto-Find`), сопряжение по QR-коду или 6-значному коду, переход с USB на Wi-Fi в 1 клик, управление флагом `Auto`/`Manual` и удаление сохранённых устройств.
  - Живые LED-индикаторы уровня сигнала (стерео L/R и микрофон), Noise Gate и тест микрофона.
  - Установка APK на телефон в один клик.

---

## 🎙 Использование телефона как микрофона для ПК

1. В Sonopipe выберите режим **«🎙 Mic Only»** или **«🎧 Duplex»**.
2. В приложении на смартфоне также переключите режим на **Mic** или **Duplex** (при первом запуске телефон запросит разрешение на запись аудио).
3. Нажмите **Start Streaming** в программе и **Start Receiver** на телефоне.
4. В ваших программах на ПК (Discord, Telegram, Steam, OBS, браузер) выберите устройство ввода:
   - В Linux: **«Monitor of Sonopipe Virtual Microphone (PC)»** или **«sonopipe_mic_sink.monitor»**.
   - На Windows: выбранный виртуальный аудиокабель.

---

## 📶 Подключение через Wireless ADB (Wi-Fi) и запоминание устройств

После первого успешного подключения по Wi-Fi Sonopipe **автоматически запоминает** ваш смартфон (модель, IP и порт) и:
- выводит чип быстрого подключения прямо на главном экране;
- автоматически переподключается к устройству в фоне при следующем запуске программы (переключатель `Auto` / `Manual` в окне **📶 Wi-Fi**).

### Способ 1: Автопоиск по mDNS (без проводов)
1. Включите *Беспроводную отладку* на телефоне (в одной Wi-Fi сети с ПК).
2. Нажмите **`⚡ Auto`** на главном экране или откройте **`📶 Wi-Fi`** → **`⚡ Auto-Find`**.

### Способ 2: Сопряжение по QR-коду или 6-значному коду (Android 11+, без проводов)
1. На телефоне: *Настройки → Параметры разработчика → Беспроводная отладка* (Wireless debugging).
2. В Sonopipe нажмите **`📶 Wi-Fi`** (или **`⋮` → `Wi-Fi Devices & Pairing`**) и выберите **`📷 QR Pair`** или **`🔑 Code`**.
3. Отсканируйте QR-код или введите код сопряжения — затем нажмите **`⚡ Auto-Find`**.

### Способ 3: Автоматический переход в 1 клик через USB (Рекомендуемый)
1. Подключите телефон к компьютеру по USB-кабелю один раз (с включённой отладкой по USB).
2. Убедитесь, что телефон и ПК подключены к одной Wi-Fi сети.
3. Нажмите **`📶 Wi-Fi` → `🔌 USB → Wi-Fi`** (или выберите пункт в меню **`⋮`**).
4. Программа сама определит Wi-Fi IP телефона, активирует порт `5555`, подключится и запомнит устройство.
5. **Отключите USB-кабель!** В следующий раз подключение произойдёт автоматически.

### Способ 3: Через терминал (CLI)
```bash
# Перевести подключенный по USB телефон в режим TCP/IP:
sonopipe --enable-tcpip 5555

# Подключиться к телефону по его Wi-Fi IP:
sonopipe --connect-wireless 192.168.1.45:5555

# Запустить стриминг микрофона через CLI:
sonopipe --cli --mode mic

# Запустить дуплексный режим (наушники + микрофон):
sonopipe --cli --mode duplex --mic-gain 1.2
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

На телефоне откроется приложение **Sonopipe**. Выберите желаемый режим (*Speaker*, *Mic*, *Duplex*) и нажмите **Start Receiver**.

### 3. Запуск трансляции звука

#### Графический интерфейс:
```bash
sonopipe
```
В окне программы выберите телефон в списке устройств, выберите режим и нажмите **Start Streaming**. Порты пробросятся автоматически.

#### Режим командной строки (CLI):
```bash
# Стриминг звука с ПК на динамики телефона (по умолчанию)
sonopipe --cli

# Только микрофон с телефона на ПК
sonopipe --cli --mode mic --mic-gain 1.5

# Дуплекс (звук ПК на телефон + микрофон телефона на ПК)
sonopipe --cli --mode duplex

# Просмотр подключенных устройств ADB (включая Wi-Fi)
sonopipe --list-adb-devices
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
│   │   ├── manager.py            # Поиск устройств, Wi-Fi connect/pair/tcpip, mDNS, port forwarding
│   │   ├── wifi_store.py         # Хранилище запомненных Wi-Fi устройств (QSettings)
│   │   ├── installer.py          # Автоматическая сборка и установка APK
│   │   └── qr_dialog.py          # Диалоги QR-кодов и 6-значного сопряжения Wireless ADB
│   ├── capture/                  # Модульная система захвата звука с ПК
│   │   ├── base.py               # Базовый интерфейс AudioCaptureBase
│   │   ├── factory.py            # Автовыбор бэкенда для текущей ОС
│   │   ├── linux_pulse.py        # Захват PipeWire / PulseAudio (parec / monitor sink)
│   │   └── windows_wasapi.py     # Захват WASAPI Loopback (Windows)
│   ├── mic/                      # Подсистема виртуального микрофона
│   │   ├── base.py               # Абстрактный интерфейс виртуального микрофона
│   │   ├── factory.py            # Выбор драйвера вирт. микрофона по ОС
│   │   ├── linux_pulse.py        # Linux: PipeWire/PulseAudio module-null-sink + pacat
│   │   ├── windows_cable.py      # Windows: маршрутизация в Virtual Audio Cable
│   │   └── receiver.py           # TCP клиент приема потока микрофона с телефона
│   ├── gui/                      # MD3 Графический интерфейс (PySide6)
│   │   ├── theme.py              # Тональные токены Material Design 3 и базовые QSS-стили
│   │   ├── main_window.py        # Главное окно, MD3-меню, чипы Wi-Fi, автопереподключение, LED-метры
│   │   ├── wifi_dialog.py        # Диалог Wi-Fi устройств, mDNS-поиска и инструкции
│   │   └── settings_dialog.py    # Настройки аудио, задержки, портов и утилит
│   ├── stream/                   # Сетевой транспорт и протокол динамиков
│   │   ├── protocol.py           # 16-байтный бинарный заголовок
│   │   └── sender.py             # TCP-клиент, регулятор громкости, стереометрия
│   ├── cli.py                    # Режим работы через терминал с поддержкой микрофона
│   └── main.py                   # Точка входа программы
├── android/                      # Android-приложение (Kotlin)
│   ├── app/src/main/java/com/adbsound/app/
│   │   ├── MainActivity.kt         # Выбор режима (Speaker/Mic/Duplex), запрос прав
│   │   ├── AudioReceiverService.kt # Двойной ServerSocket (Speaker: 12850, Mic: 12851)
│   │   ├── AudioRecordSource.kt    # Захват микрофона AudioRecord + EchoCanceler + NoiseSuppressor
│   │   ├── AudioTrackPlayer.kt     # Низколатентный AudioTrack
│   │   └── AdbProtocol.kt          # Парсер протокола заголовков
│   └── build.gradle.kts
├── apk/                          # Предсобранный готовый APK
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
| `Connection refused at 127.0.0.1:12850` / `12851` | На телефоне не нажат «Start Receiver» или не совпадает режим | Убедитесь, что на телефоне нажат **Start Receiver** и выбран нужный режим (*Mic*, *Speaker* или *Duplex*) |
| Микрофон не слышно в Discord / браузере | В настройках программы выбран стандартный микрофон | В настройках звука выберите устройство ввода **«sonopipe_mic_sink.monitor»** или **«Sonopipe Virtual Microphone»** |
| `failed to connect to IP:5555` | Порт 5555 не открыт на телефоне или устройство не в одной сети Wi-Fi | Проверьте подключение к общему Wi-Fi и выполните `⚡ Switch to Wi-Fi via USB` при подключенном кабеле |
| `adb: command not found` | Не установлены утилиты Android platform-tools | `sudo pacman -S android-tools` (Arch) или `sudo apt install adb` (Ubuntu) |
| Задержка звука по Wi-Fi | Нагруженная сеть Wi-Fi | Переключитесь на 5 ГГц Wi-Fi или используйте проводной USB-режим |

---

## 📄 Лицензия

MIT License © 2026. Свободно для использования и модификации.

#include <EEPROM.h>
#include <RTClib.h>
#include <TM1637Display.h>

// EEPROM addresses
#define EEPROM_ALARM_AM_HOUR 0
#define EEPROM_ALARM_AM_MIN 1
#define EEPROM_ALARM_PM_HOUR 2
#define EEPROM_ALARM_PM_MIN 3

#define RELAY_PIN 5
#define BUTTON_A_PIN 12
#define BUTTON_B_PIN 11
#define DETECTED_SIGNAL_PIN 6
#define GO_SIGNAL_PIN 7
#define CLK_PIN 9
#define DIO_PIN 10

RTC_DS3231 rtc;
TM1637Display display(CLK_PIN, DIO_PIN);

// Define modes
enum Mode {
  NORMAL,               // Normal mode (showing hour/minute)
  SETTING,              // Setting mode (choose hour or minute)
};

enum CLKMode {
  HOUR,
  MINUTE,
  _NORMAL_
};

enum TM1637brightness {
  UP,
  DOWN
};

Mode currentMode = NORMAL;
CLKMode timeModeToDisplay = _NORMAL_;
TM1637brightness brightness = DOWN;

const unsigned long alarmDuration = 30UL * 60UL * 1000UL; // 30 minutes in milliseconds
const long pumpingInterval = 60000;
unsigned long timerStartMillis = 0,
              recordPressedTime = 0,
              lastDebounceTime = 0,
              pumpStartTime = 0,
              lastSerialPrintTime = 0;
bool RPT_state = false,
     waterpump_status = false,
     detection_status = false,
     pumpRunning = false,
     startAlarmState = false,
     timerStarted = false;
int start_alarmAM[2] = { 8, 0 },                    // 8 = hour, 0 = minute
    start_alarmPM[2] = { 5, 0 };                    // 5 = hour, 0 = minute
int recordMinute = 90,
    recordSecond = 90,
    debounceDelay = 50;

// Define the custom characters for "P" and "A"
uint8_t P[] = {
  B11111100,  // Segment A
  B11111100,  // Segment B
  B10010000,  // Segment C
  B10010000,  // Segment D
  B11110000,  // Segment E
  B10010000,  // Segment F
  B10010000   // Segment G
};

uint8_t A[] = {
  B11111100,  // Segment A
  B11111100,  // Segment B
  B10000000,  // Segment C
  B10000000,  // Segment D
  B11111100,  // Segment E
  B10010000,  // Segment F
  B10010000   // Segment G
};

void saveAlarmsToEEPROM() {
  // Save Alarm AM
  EEPROM.update(EEPROM_ALARM_AM_HOUR, start_alarmAM[0]);
  EEPROM.update(EEPROM_ALARM_AM_MIN, start_alarmAM[1]);
  
  // Save Alarm PM
  EEPROM.update(EEPROM_ALARM_PM_HOUR, start_alarmPM[0]);
  EEPROM.update(EEPROM_ALARM_PM_MIN, start_alarmPM[1]);
}

void loadAlarmsFromEEPROM() {
  // Check if EEPROM has been initialized (if value is 255, it hasn't been written to)
  if (EEPROM.read(EEPROM_ALARM_AM_HOUR) != 255) {
    // Load Alarm AM
    start_alarmAM[0] = EEPROM.read(EEPROM_ALARM_AM_HOUR);
    start_alarmAM[1] = EEPROM.read(EEPROM_ALARM_AM_MIN);
    
    // Load Alarm PM
    start_alarmPM[0] = EEPROM.read(EEPROM_ALARM_PM_HOUR);
    start_alarmPM[1] = EEPROM.read(EEPROM_ALARM_PM_MIN);
    
    // Validate loaded values
    validateAlarmValues(start_alarmAM);
    validateAlarmValues(start_alarmPM);
  }
}

void validateAlarmValues(int* alarm) {
  // Make sure the hour is between 1 and 12
  if (alarm[0] < 1 || alarm[0] > 12) alarm[0] = 8;
  
  // Make sure minute is between 0 and 59
  if (alarm[1] < 0 || alarm[1] > 59) alarm[1] = 0;
}

void setup() {
  Serial.begin(115200);
  initialized_used_pins();
  test_TM1637();
  check_RTC();
  
  // Load saved alarm settings from EEPROM
  loadAlarmsFromEEPROM();
}

void triggerWaterPump() {
  if (!pumpRunning) {
    // Start the water pump
    digitalWrite(RELAY_PIN, LOW);  // Turn the pump on
    pumpStartTime = millis();      // Record the start time
    pumpRunning = true;            // Set pump status as running
    Serial.println("Pump started");
  }
}

void serialDisplay(bool detected_state, int currentHour, int currentMinute, String currentMeridiem) {
  unsigned long currentMillis = millis();

  if (currentMillis - lastSerialPrintTime >= 1000) {
    if (brightness == UP) {
      display.setBrightness(2, true);
      brightness = DOWN;
    } else {
      display.setBrightness(7, true);
      brightness = UP;
    }
    TM1637_diplay(currentHour, currentMinute);
    Serial.println("Alarm AM: " + String(start_alarmAM[0]) + ":" + String(start_alarmAM[1]) + " AM");
    Serial.println("Alarm PM: " + String(start_alarmPM[0]) + ":" + String(start_alarmPM[1]) + " PM");
    Serial.println("Current Time: " + String(currentHour) + ":" + String(currentMinute) + " " + currentMeridiem);
    Serial.print("detected_state: ");
    Serial.println(detected_state ? "true\n" : "false\n");
    lastSerialPrintTime = currentMillis;  // Update the last print time
  }
}

void loop() {
  handleAlarmSetting(detection_status);

  if (currentMode == SETTING) {
    return;
  }

  DateTime now = rtc.now();
  int currentHour = now.hour(),
      currentMinute = now.minute(),
      currentSecond = now.second();
  String currentMeridiem = normalizeTo12HourFormat(currentHour);
  bool detected_state = !digitalRead(DETECTED_SIGNAL_PIN);

  serialDisplay(detected_state, currentHour, currentMinute, currentMeridiem);


  if (!timerStarted) {
    startAlarmState = checkCurrTimeAndTrig(currentHour, currentMinute, currentMeridiem);
    
    if (startAlarmState) {
      timerStarted = true;
      timerStartMillis = millis();
      // Trigger your alarm logic here
      waterpump_status = true;
      detection_status = true;
      digitalWrite(GO_SIGNAL_PIN, HIGH);
      Serial.println("Alarm started!");
    }
  }

  if (waterpump_status && !pumpRunning) {
    triggerWaterPump();
    waterpump_status = false;
  }

  // If timer is running, check if time has passed
  if (timerStarted) {
    if (millis() - timerStartMillis >= alarmDuration) {
      // Timer complete
      timerStarted = false;
      startAlarmState = false;
      detected_state = false;
      digitalWrite(GO_SIGNAL_PIN, LOW);
      // Optionally reset or handle alarm completion
      Serial.println("Alarm finished after 30 mins.");
    }
  }


  if (detection_status && detected_state && !pumpRunning) {
    triggerWaterPump();
  }

  // Check if the specified time interval has passed (1 minute)
  if (pumpRunning && (millis() - pumpStartTime >= pumpingInterval)) {
    digitalWrite(RELAY_PIN, HIGH); // Turn the pump off
    pumpRunning = false;           // Reset pump status
    Serial.println("Pump stopped");
  }
}

void test_TM1637() {
  display.setBrightness(0x0c);
  display.showNumberDecEx(0, 0b01000000, true);
  delay(1000);
}

void initialized_used_pins() {
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH);  // Initialize relay to OFF state
  
  pinMode(BUTTON_A_PIN, INPUT_PULLUP);
  pinMode(BUTTON_B_PIN, INPUT_PULLUP);
  pinMode(DETECTED_SIGNAL_PIN, INPUT_PULLUP);
  
  pinMode(GO_SIGNAL_PIN, OUTPUT);
  digitalWrite(GO_SIGNAL_PIN, LOW);  // Initialize GO signal to LOW
}

void check_RTC() {
  if (!rtc.begin()) {
    Serial.println("RTC not found!");
    
    while (true) {
      for (byte countDown = 7; countDown > 0; countDown--) {
        display.setBrightness(countDown, true);
        delay(1000);
      }
    }
  }
}

String normalizeTo12HourFormat(int& currentHour) {
  String currentMeridiem;

  if (currentHour == 0) {
    currentHour = 12;  // Midnight is 12 AM
    currentMeridiem = "AM";
  } else if (currentHour == 12) {
    currentMeridiem = "PM";  // Noon is 12 PM
  } else if (currentHour > 12) {
    currentHour -= 12;  // Convert to 12-hour format (PM)
    currentMeridiem = "PM";
  } else {
    currentMeridiem = "AM";  // Morning time (AM)
  }

  return currentMeridiem;
}

bool checkCurrTimeAndTrig(const int currentHour, const int currentMinute, const String currentMeridiem) {
  return (start_alarmAM[0] == currentHour && start_alarmAM[1] == currentMinute && currentMeridiem.equals("AM")) ||
         (start_alarmPM[0] == currentHour && start_alarmPM[1] == currentMinute && currentMeridiem.equals("PM"));
}

void handleAlarmSetting(bool detection_status) {
  if (detection_status) {
    currentMode = NORMAL;
    RPT_state = false;
    return;
  }
  
  bool buttonState1 = !digitalRead(BUTTON_A_PIN);  // Button A is pressed
  bool buttonState2 = !digitalRead(BUTTON_B_PIN);  // Button B is pressed

  // Check if both buttons are pressed and start the timer if not already started
  if ((buttonState1 && buttonState2) && !RPT_state) {
    if (millis() - lastDebounceTime > debounceDelay) {  // Debounce check
      recordPressedTime = millis();  // Record the time when both buttons were pressed
      RPT_state = true;             // Indicate that the timer has started
      lastDebounceTime = millis();  // Reset debounce time
    }
  }

  // RESET - If either button is released, reset the counter and timer
  if (!(buttonState1 && buttonState2)) {
    RPT_state = false;     // Stop counting when buttons are released
    recordPressedTime = 0;  // Reset the time when buttons are released
  }

  // Check if 5000 ms (5 seconds) have passed since both buttons were pressed
  if (RPT_state && (millis() - recordPressedTime) >= 5000) {
    display.showNumberDecEx(0, 0b01000000, true);
    delay(2000);
    currentMode = SETTING; // Trigger the alarm or any other action after 5000 ms
    RPT_state = false;  // Stop counting after the alarm is set
    handleSetAlarms();
    currentMode = NORMAL;
    timeModeToDisplay = _NORMAL_;
  }
}

void handleSetAlarms() {
  enum Staging {
    SET_AM,
    SET_PM,
    SET_END
  };
  Staging currentStage = SET_AM;

  while (true) {
    switch(currentStage) {
      case SET_AM:
        // Flash "A" for AM alarm
        display.clear();
        display.setSegments(A, 3, 1);
        modifyAlarm(start_alarmAM); 
        currentStage = SET_PM;
        break;

      case SET_PM: 
        // Flash "P" for PM alarm
        display.clear();
        display.setSegments(P, 3, 1);
        modifyAlarm(start_alarmPM);
        currentStage = SET_END;
        break;

      default: 
        timeModeToDisplay = _NORMAL_; 
        display.clear();
        display.showNumberDec(8888, true); // Show all segments briefly to confirm exit
        delay(500);
        display.clear();
        return;
    }
  } 
}

void modifyAlarm(int* alarm) {
  byte staging = 0;
  delay(500);  // Wait for half a second
  display.clear();  // Clear the display to simulate flashing
  
  while (true) {
    bool read_btn_A = !digitalRead(BUTTON_A_PIN);
    bool read_btn_B = !digitalRead(BUTTON_B_PIN);
    delay(1000); // Short delay for button responsiveness

    if (read_btn_A && read_btn_B) staging++;
    getDigitType(staging);

    switch (staging) {
      case 0:  // set hour
        if (read_btn_A && !read_btn_B) {
          alarm[0]++;
          if (alarm[0] > 12) alarm[0] = 1;  // Hour limit (1-12)
        } else if (!read_btn_A && read_btn_B) {
          alarm[0]--;
          if (alarm[0] < 1) alarm[0] = 12;  // Hour limit (1-12)
        }
        TM1637_diplay(alarm[0], 0);
        break;

      case 1:  // set minute
        if (read_btn_A && !read_btn_B) {
          alarm[1]++;
          if (alarm[1] > 59) alarm[1] = 0;  // Minute limit (0-59)
        } else if (!read_btn_A && read_btn_B) {
          alarm[1]--;
          if (alarm[1] < 0) alarm[1] = 59;  // Minute limit (0-59)
        }
        TM1637_diplay(0, alarm[1]);
        break;

      default:
        break;
    }

    if (staging > 1) {
      // Save settings to EEPROM before exiting
      saveAlarmsToEEPROM();
      // Show confirmation
      display.clear();
      display.showNumberDec(8888, true); // Show all segments briefly
      delay(500);
      display.clear();
      break;  // Exit setup loop when finished
    }
  }
}

void getDigitType(const byte stage) {
  switch (stage) {
      case 0:
        timeModeToDisplay = HOUR;
        return;
      case 1: 
        timeModeToDisplay = MINUTE;
        return;
      case 2: 
        timeModeToDisplay = _NORMAL_;
        return;
  }
}

void TM1637_diplay(const int hour, const int minute) {
  switch(timeModeToDisplay) {
    case HOUR:
      display.clear();
      display.showNumberDec(hour, false, 2, 0);
      break;

    case MINUTE:
      display.clear();
      display.showNumberDec(minute, false, 2, 2);
      break;

    case _NORMAL_:
      // Format: HH:MM with colon
      // Use showNumberDecEx to show the colon (0b01000000)
      display.showNumberDecEx(hour * 100 + minute, 0b01000000, true);
      break;
  }
}
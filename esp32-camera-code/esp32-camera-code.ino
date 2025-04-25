// Replace with your network credentials
// const char* ssid = "Your_SSID";
// const char* password = "Your_PASSWORD";
#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <esp_timer.h>
#include <img_converters.h>
#include <esp_http_server.h>

#define ESP_LED 4
#define GPIO_13 13
#define GPIO_12 12
bool goDetect = false;

// ==== CAMERA SETTINGS ====
// ==== Pin configuration for AI Thinker ESP32-CAM ====
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27

#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

// ==== WIFI SETTINGS ====
const char *ssid = "Matheeeeeet";
const char *password = "123456777";

// Static IP config (change as needed)
IPAddress local_IP(192, 168, 1, 184);  // Static IP
IPAddress gateway(192, 168, 1, 1);
IPAddress subnet(255, 255, 255, 0);

// ==== HTTP SERVER ====
WebServer server(5000);  // For notification handling

// ==== CAMERA STREAM HANDLER ====
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t *fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len;
  uint8_t *_jpg_buf;
  char *part_buf[64];

  res = httpd_resp_set_type(req, "multipart/x-mixed-replace; boundary=frame");
  if (res != ESP_OK) {
    return res;
  }

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Camera capture failed");
      return ESP_FAIL;
    }

    if (fb->format != PIXFORMAT_JPEG) {
      bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
      esp_camera_fb_return(fb);
      if (!jpeg_converted) {
        Serial.println("JPEG compression failed");
        return ESP_FAIL;
      }
    } else {
      _jpg_buf_len = fb->len;
      _jpg_buf = fb->buf;
    }

    size_t hlen = snprintf((char *)part_buf, 64, "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", (uint32_t)_jpg_buf_len);
    res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
    res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    res = httpd_resp_send_chunk(req, "\r\n", 2);

    if (fb->format != PIXFORMAT_JPEG) {
      free(_jpg_buf);
    }
    esp_camera_fb_return(fb);

    if (res != ESP_OK) {
      break;
    }
  }

  return res;
}

// ==== START CAMERA STREAM SERVER ====
void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 81;

  httpd_uri_t stream_uri = {
    .uri = "/stream",
    .method = HTTP_GET,
    .handler = stream_handler,
    .user_ctx = NULL
  };

  httpd_handle_t stream_httpd = NULL;
  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    Serial.println("📡 Camera stream server started at /stream");
  } else {
    Serial.println("❌ Failed to start stream server");
  }
}

String extractMsg(const String msg) {
  String getStr = "";
  bool colon = false;
  for (int i = 0; msg[i] != ','; i++) {
    if (colon) {
      getStr += msg[i];
    }

    if (msg[i] == ':') {
      colon = true;
    }
  }
  getStr.trim();

  String finalMsg = "";
  for (int i = 0; getStr[i] != '\0'; i++) {
    if (getStr[i] != '"') {
      finalMsg += getStr[i];
    }
  }
  return finalMsg;
}

// ==== NOTIFICATION HANDLER ====
void handleNotify() {
  if (server.hasArg("plain")) {
    String msg = server.arg("plain");
    Serial.println("📨 Received notification: " + msg);
    String extractedMsg = extractMsg(msg);

    // Blink LED as a visual alert
    if (extractedMsg == "TEST ALERT") {
      digitalWrite(ESP_LED, HIGH);  // Turn on LED
      delay(200);                   // Wait 500 ms
      digitalWrite(ESP_LED, LOW);   // Turn off LED
    }

    if (goDetect) {
      if (extractedMsg == "uncleaned-pig detected" || extractedMsg == "dirt detected") {
        digitalWrite(GPIO_12, HIGH);  // Turn on LED
        delay(2000);                   // Wait 500 ms
        digitalWrite(GPIO_12, LOW);  // Turn on LED
      }
    }
  } else {
    Serial.println("⚠️ Received notification with no content");
  }
  server.send(200, "text/plain", "OK");
}

void setup() {
  pinMode(ESP_LED, OUTPUT);
  pinMode(GPIO_12, OUTPUT);
  pinMode(GPIO_13, INPUT_PULLUP);

  Serial.begin(115200);
  delay(1000);

  // Set static IP
  if (!WiFi.config(local_IP, gateway, subnet)) {
    Serial.println("⚠️ Failed to configure static IP");
  }

  WiFi.begin(ssid, password);
  Serial.print("Connecting to Wi-Fi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\n✅ Wi-Fi connected");
  Serial.println("IP address: " + WiFi.localIP().toString());

  // Camera config
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 10;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_CIF;
    config.jpeg_quality = 12;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("❌ Camera init failed with error 0x%x\n", err);
    return;
  }

  Serial.println("✅ Camera init OK!");

  // Start servers
  server.on("/notify", HTTP_POST, handleNotify);
  server.begin();
  Serial.println("🔔 HTTP server started at port 5000");

  startCameraServer();  // MJPEG stream at :81/stream
}

void loop() {
  server.handleClient();            // Handle notification endpoint
  goDetect = !digitalRead(GPIO_13);  // Check if Arduino go signal
}

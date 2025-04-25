import cv2
import requests
import customtkinter as ctk
from PIL import Image, ImageTk
from ultralytics import YOLO
import time
import os
import threading
from datetime import datetime
from src.mylib import object_detection

class SwineDetectionSystem:
    def __init__(self):
        # Constants
        self.ESP32_STREAM_URL = "http://192.168.1.184:81/stream"
        self.NOTIFY_URL = "http://192.168.1.184:5000/notify"
        self.MODEL_PATH = "src/utils/best.pt"
        self.CLASS_FILE = "src/utils/class.names"
        self.FRAME_WIDTH, self.FRAME_HEIGHT = 960, 720
        self.CONFIDENCE_THRESHOLD = 0.15
        self.COOLDOWN_SECONDS = 10
        self.APP_TITLE = "Swine Detection System"
        self.LOG_DIRECTORY = "logs"

        # Camera sources
        self.camera_sources = {
            "ESP32 Camera": self.ESP32_STREAM_URL,
            "PC Camera": 0,  # Default PC camera index
            "Custom URL": ""  # Will be set by user
        }
        self.current_camera_source = "ESP32 Camera"

        # Global variables
        self.capture = None
        self.yolo_model = None
        self.class_names = []
        self.last_notify_time = 0
        self.detection_active = True
        self.current_fps = 0
        self.last_frame_time = 0
        self.fps_update_time = 0
        self.current_frame = None
        self.detection_counts = {"clean": 0, "uncleaned": 0, "dirt": 0, "total": 0}
        self.app_running = True
        self.detection_thread = None

        # Create directories if they don't exist
        os.makedirs(self.LOG_DIRECTORY, exist_ok=True)

        # Setup GUI
        self.setup_gui()

    def setup_gui(self):
        """Set up the GUI components"""
        # GUI Setup
        ctk.set_appearance_mode("Gray")
        ctk.set_default_color_theme("blue")

        self.app = ctk.CTk()
        self.app.title(self.APP_TITLE)
        self.app.geometry("1200x800")
        self.app.grid_columnconfigure(0, weight=1)
        self.app.grid_rowconfigure(0, weight=1)

        # Create main frame
        main_frame = ctk.CTkFrame(self.app)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main_frame.grid_columnconfigure(0, weight=5)
        main_frame.grid_columnconfigure(1, weight=2)
        main_frame.grid_rowconfigure(0, weight=3)
        main_frame.grid_rowconfigure(1, weight=1)

        # Left section - Video display and status
        left_frame = ctk.CTkFrame(main_frame)
        left_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=5, pady=5)
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        video_frame = ctk.CTkFrame(left_frame)
        video_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        video_frame.grid_rowconfigure(0, weight=1)
        video_frame.grid_columnconfigure(0, weight=1)

        self.video_label = ctk.CTkLabel(video_frame, text="")
        self.video_label.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        status_frame = ctk.CTkFrame(video_frame)
        status_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        status_frame.grid_columnconfigure(0, weight=1)
        status_frame.grid_columnconfigure(1, weight=1)

        self.connection_indicator = ctk.CTkLabel(status_frame, text="⚫ Camera: Connecting", font=("Arial", 12))
        self.connection_indicator.grid(row=0, column=0, sticky="w", padx=10, pady=5)

        self.detection_indicator = ctk.CTkLabel(status_frame, text="🔍 No pigs detected", font=("Arial", 12))
        self.detection_indicator.grid(row=0, column=1, sticky="e", padx=10, pady=5)

        self.fps_indicator = ctk.CTkLabel(status_frame, text="FPS: 0.0", font=("Arial", 12))
        self.fps_indicator.grid(row=0, column=2, sticky="e", padx=10, pady=5)

        # Right section - Statistics and controls
        right_frame = ctk.CTkFrame(main_frame)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        right_frame.grid_rowconfigure(0, weight=0)
        right_frame.grid_columnconfigure(0, weight=1)

        stats_label = ctk.CTkLabel(right_frame, text="Detection Statistics", font=("Arial", 16, "bold"))
        stats_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        stats_frame = ctk.CTkFrame(right_frame)
        stats_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        stats_frame.grid_columnconfigure(0, weight=1)
        stats_frame.grid_columnconfigure(1, weight=1)

        self.total_detections = ctk.CTkLabel(stats_frame, text="Total Detections: 0", font=("Arial", 14))
        self.total_detections.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        self.clean_detections = ctk.CTkLabel(stats_frame, text="Clean Pigs: 0", font=("Arial", 14))
        self.clean_detections.grid(row=1, column=0, sticky="w", padx=10, pady=5)

        self.uncleaned_detections = ctk.CTkLabel(stats_frame, text="Uncleaned Pigs: 0", font=("Arial", 14), text_color="#FF5555")
        self.uncleaned_detections.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        self.dirt_detections = ctk.CTkLabel(stats_frame, text="Dirt: 0", font=("Arial", 14))
        self.dirt_detections.grid(row=2, column=0, sticky="w", padx=10, pady=5)

        # Camera settings section
        camera_frame = ctk.CTkFrame(right_frame)
        camera_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        camera_frame.grid_columnconfigure(0, weight=1)
        camera_frame.grid_columnconfigure(1, weight=2)

        camera_label = ctk.CTkLabel(camera_frame, text="Camera Settings", font=("Arial", 14, "bold"))
        camera_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        # Camera source dropdown
        source_label = ctk.CTkLabel(camera_frame, text="Camera Source:")
        source_label.grid(row=1, column=0, sticky="w", padx=10, pady=5)

        self.camera_source_var = ctk.StringVar(value=self.current_camera_source)
        self.camera_source_dropdown = ctk.CTkOptionMenu(
            camera_frame, 
            values=list(self.camera_sources.keys()),
            variable=self.camera_source_var,
            command=self.on_camera_source_changed
        )
        self.camera_source_dropdown.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        # Custom URL entry
        url_label = ctk.CTkLabel(camera_frame, text="Custom URL:")
        url_label.grid(row=2, column=0, sticky="w", padx=10, pady=5)

        self.custom_url_entry = ctk.CTkEntry(camera_frame, width=200)
        self.custom_url_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        self.custom_url_entry.insert(0, "http://")

        # PC Camera index entry
        pc_cam_label = ctk.CTkLabel(camera_frame, text="PC Camera Index:")
        pc_cam_label.grid(row=3, column=0, sticky="w", padx=10, pady=5)

        self.pc_camera_var = ctk.StringVar(value="0")
        self.pc_camera_entry = ctk.CTkEntry(camera_frame, width=50, textvariable=self.pc_camera_var)
        self.pc_camera_entry.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        # Connect button
        self.connect_button = ctk.CTkButton(camera_frame, text="Connect Camera", command=self.connect_camera)
        self.connect_button.grid(row=4, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        # Settings section
        settings_frame = ctk.CTkFrame(right_frame)
        settings_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=10)
        settings_frame.grid_columnconfigure(0, weight=1)
        settings_frame.grid_columnconfigure(1, weight=2)

        settings_label = ctk.CTkLabel(settings_frame, text="Settings", font=("Arial", 14, "bold"))
        settings_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        # Confidence threshold slider
        conf_label = ctk.CTkLabel(settings_frame, text="Confidence:")
        conf_label.grid(row=1, column=0, sticky="w", padx=10, pady=5)

        self.conf_slider = ctk.CTkSlider(settings_frame, from_=0.05, to=0.95, number_of_steps=18, command=self.update_confidence)
        self.conf_slider.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.conf_slider.set(self.CONFIDENCE_THRESHOLD)

        self.conf_value = ctk.CTkLabel(settings_frame, text=f"{self.CONFIDENCE_THRESHOLD:.2f}")
        self.conf_value.grid(row=1, column=2, padx=5, pady=5)

        # Cooldown slider
        cooldown_label = ctk.CTkLabel(settings_frame, text="Alert Cooldown:")
        cooldown_label.grid(row=2, column=0, sticky="w", padx=10, pady=5)

        self.cooldown_slider = ctk.CTkSlider(settings_frame, from_=5, to=60, number_of_steps=11, command=self.update_cooldown)
        self.cooldown_slider.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        self.cooldown_slider.set(self.COOLDOWN_SECONDS)

        self.cooldown_value = ctk.CTkLabel(settings_frame, text=f"{self.COOLDOWN_SECONDS}s")
        self.cooldown_value.grid(row=2, column=2, padx=5, pady=5)

        # Control buttons
        controls_frame = ctk.CTkFrame(right_frame)
        controls_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=10)
        controls_frame.grid_columnconfigure(0, weight=1)
        controls_frame.grid_columnconfigure(1, weight=1)

        self.toggle_button = ctk.CTkButton(controls_frame, text="Pause Detection", command=self.toggle_detection, fg_color="#2B7539")
        self.toggle_button.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        test_button = ctk.CTkButton(controls_frame, text="Test Alert", command=lambda: self.send_notification(test=True))
        test_button.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        reset_button = ctk.CTkButton(controls_frame, text="Reset Stats", command=self.reset_stats)
        reset_button.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        # Log section
        log_frame = ctk.CTkFrame(main_frame)
        log_frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        log_label = ctk.CTkLabel(log_frame, text="System Log", font=("Arial", 14, "bold"))
        log_label.grid(row=0, column=0, sticky="w", padx=10, pady=(5, 0))

        self.log_box = ctk.CTkTextbox(log_frame, height=100, font=("Consolas", 12))
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 10))

        # Set up window close handler
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_camera_source_changed(self, source):
        """Handle camera source dropdown change"""
        self.current_camera_source = source
        self.log_message(f"Camera source changed to: {source}")

    def connect_camera(self):
        """Connect to the selected camera source"""
        # Release any existing camera
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        
        try:
            camera_source = self.current_camera_source
            self.connection_indicator.configure(text="🟠 Camera: Connecting", text_color="orange")
            
            if camera_source == "ESP32 Camera":
                url = self.ESP32_STREAM_URL
                self.log_message(f"Connecting to ESP32 camera at {url}...")
                self.capture = object_detection.load_camera(url)
                
            elif camera_source == "PC Camera":
                index = int(self.pc_camera_var.get())
                self.log_message(f"Connecting to PC camera (index: {index})...")
                self.capture = cv2.VideoCapture(index)
                
            elif camera_source == "Custom URL":
                url = self.custom_url_entry.get()
                if not url or url == "http://":
                    self.log_message("❌ Please enter a valid URL")
                    self.connection_indicator.configure(text="⚫ Camera: Disconnected", text_color="red")
                    return
                
                self.log_message(f"Connecting to custom URL: {url}...")
                self.camera_sources["Custom URL"] = url
                self.capture = object_detection.load_camera(url)
            
            # Check if camera opened successfully
            if self.capture is None or not self.capture.isOpened():
                self.log_message("❌ Failed to connect to camera")
                self.connection_indicator.configure(text="⚫ Camera: Disconnected", text_color="red")
                return
            
            self.connection_indicator.configure(text="🟢 Camera: Connected", text_color="green")
            self.log_message(f"✓ Successfully connected to {camera_source}")
            
        except Exception as e:
            self.log_message(f"❌ Camera connection error: {str(e)}")
            self.connection_indicator.configure(text="⚫ Camera: Disconnected", text_color="red")

    def update_confidence(self, value):
        """Update confidence threshold from slider"""
        self.CONFIDENCE_THRESHOLD = float(value)
        self.conf_value.configure(text=f"{float(value):.2f}")

    def update_cooldown(self, value):
        """Update alert cooldown from slider"""
        self.COOLDOWN_SECONDS = int(float(value))
        self.cooldown_value.configure(text=f"{self.COOLDOWN_SECONDS}s")

    def toggle_detection(self):
        """Toggle detection on/off"""
        self.detection_active = not self.detection_active
        if self.detection_active:
            self.toggle_button.configure(text="Pause Detection", fg_color="#2B7539")
            self.log_message("Detection resumed")
        else:
            self.toggle_button.configure(text="Resume Detection", fg_color="#8B8000")
            self.log_message("Detection paused")

    def reset_stats(self):
        """Reset detection statistics"""
        self.detection_counts = {"clean": 0, "uncleaned": 0, "dirt": 0, "total": 0}
        self.update_stats_display()
        self.log_message("Statistics reset")

    def log_message(self, message, save_to_file=True):
        """Add a timestamped message to the log box and optionally to a file"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        
        # Add to UI log
        try:
            self.log_box.insert("end", log_entry + "\n")
            self.log_box.see("end")
        except Exception:
            # If GUI is not available yet or already destroyed
            print(log_entry)
        
        # Save to file if enabled
        if save_to_file:
            date_str = time.strftime("%Y-%m-%d")
            log_file = f"{self.LOG_DIRECTORY}/detection_log_{date_str}.txt"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry + "\n")

    def update_stats_display(self):
        """Update the statistics display with current detection counts"""
        self.total_detections.configure(text=f"Total Detections: {self.detection_counts['total']}")
        self.clean_detections.configure(text=f"Clean Pigs: {self.detection_counts['clean']}")
        self.uncleaned_detections.configure(text=f"Uncleaned Pigs: {self.detection_counts['uncleaned']}")
        self.dirt_detections.configure(text=f"Dirt: {self.detection_counts['dirt']}")

    def send_notification(self, test=False):
        """Send notification to ESP32"""
        # Skip if on cooldown (unless it's a test)
        if not test and (time.time() - self.last_notify_time < self.COOLDOWN_SECONDS):
            return
        
        try:
            message = "TEST ALERT" if test else "uncleaned-pig detected"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            payload = {"message": message, "timestamp": timestamp}
            
            response = requests.post(self.NOTIFY_URL, json=payload, timeout=5)
            
            if response.status_code == 200:
                self.log_message(f"📨 Alert sent: '{message}'")
                self.last_notify_time = time.time()
            else:
                self.log_message(f"⚠️ Alert send failed: HTTP {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.log_message(f"❌ Error sending notification: {str(e)}")

    def initialize_system(self):
        """Initialize the model and camera"""
        try:
            self.log_message("System starting...")
            
            # Check if model file exists
            if not os.path.exists(self.MODEL_PATH):
                self.log_message(f"❌ Model not found at {self.MODEL_PATH}")
                return False
                
            # Check if class file exists
            if not os.path.exists(self.CLASS_FILE):
                self.log_message(f"❌ Class names file not found at {self.CLASS_FILE}")
                return False
            
            # Load YOLO model
            self.log_message("Loading YOLO model...")
            self.yolo_model = YOLO(self.MODEL_PATH)
            
            # Load class names
            self.log_message("Loading class names...")
            self.class_names = object_detection.read_class_names(self.CLASS_FILE)
            if len(self.class_names) > 0:
                self.log_message(f"Loaded {len(self.class_names)} classes: {', '.join(self.class_names[:3] if len(self.class_names) > 3 else self.class_names)}...")
            else:
                self.log_message("⚠️ No classes loaded from class file")
                return False
            
            # Connect to default camera
            self.connect_camera()
            
            self.log_message("✓ System initialized successfully")
            return True
            
        except Exception as e:
            self.log_message(f"❌ Error during initialization: {str(e)}")
            return False

    def process_detection(self, frame):
        """Process detection on a frame"""
        if not self.detection_active:
            return frame, False, False
        
        try:
            # Run YOLO detection
            boxes = object_detection.get_prediction_boxes(frame, self.yolo_model, self.CONFIDENCE_THRESHOLD)
            
            # Draw boxes and track objects
            frame, detected_objects, count_cls = object_detection.track_objects(frame, boxes, self.class_names)

            self.detection_counts["clean"] = count_cls.get("clean", 0)
            self.detection_counts["uncleaned"] = count_cls.get("uncleaned", 0)
            self.detection_counts["dirt"] = count_cls.get("dirt", 0)
            self.detection_counts["total"] = count_cls.get("total", 0)

            # Check for uncleaned pigs
            uncleaned_found = 'uncleaned-pig' in detected_objects
            dirt_found = 'dirt' in detected_objects
            clean_found = 'clean-pig' in detected_objects

            return frame, clean_found, uncleaned_found, dirt_found
            
        except Exception as e:
            self.log_message(f"⚠️ Detection error: {str(e)}")
            return frame, False, False

    def detection_loop(self):
        """Separate thread for continuous detection"""
        reconnect_attempts = 0
        max_reconnect_attempts = 5
        reconnect_delay = 5  # seconds
        
        while self.app_running:
            loop_start = time.time()
            
            # Check if camera is connected
            if self.capture is None or not self.capture.isOpened():
                if reconnect_attempts >= max_reconnect_attempts:
                    self.log_message(f"❌ Failed to reconnect after {max_reconnect_attempts} attempts, waiting longer...")
                    time.sleep(30)  # Wait longer before next batch of attempts
                    reconnect_attempts = 0
                
                try:
                    reconnect_attempts += 1
                    self.log_message(f"Attempting to reconnect to camera (attempt {reconnect_attempts}/{max_reconnect_attempts})...")
                    self.app.after(0, lambda: self.connection_indicator.configure(text="🟠 Camera: Reconnecting", text_color="orange"))
                    
                    # Attempt to reconnect to the current camera source
                    self.connect_camera()
                    
                    if self.capture is None or not self.capture.isOpened():
                        time.sleep(reconnect_delay)
                        continue
                        
                except Exception as e:
                    self.log_message(f"❌ Reconnection error: {str(e)}")
                    self.app.after(0, lambda: self.connection_indicator.configure(text="⚫ Camera: Disconnected", text_color="red"))
                    time.sleep(reconnect_delay)
                    continue
            
            try:
                # Read frame
                ret, frame = self.capture.read()
                if not ret or frame is None:
                    self.log_message("⚠️ Empty frame received")
                    # Possibly camera disconnected
                    self.capture = None
                    continue
                    
                # Process frame
                frame = cv2.resize(frame, (self.FRAME_WIDTH, self.FRAME_HEIGHT))
                self.current_frame = frame.copy()  # Store a copy for potential processing
                
                # Only run detection if active
                if self.detection_active:
                    frame, clean_found, uncleaned_found, dirt_found = self.process_detection(frame)
                    
                    # Update detection indicator
                    if uncleaned_found or dirt_found:
                        if uncleaned_found and dirt_found: 
                            self.app.after(0, lambda: self.detection_indicator.configure(text="⚠️ Dirt and uncleaned pigs detected!", text_color="red"))
                        elif uncleaned_found:
                            self.app.after(0, lambda: self.detection_indicator.configure(text="⚠️ Uncleaned detected!", text_color="red"))
                        else:
                            self.app.after(0, lambda: self.detection_indicator.configure(text="⚠️ Dirt detected!", text_color="red"))

                        # Send notification if enough time has passed
                        if time.time() - self.last_notify_time > self.COOLDOWN_SECONDS:
                            self.send_notification()
                    elif clean_found:
                        self.app.after(0, lambda: self.detection_indicator.configure(text="🐖 Clean pigs detected", text_color="green"))
                    else:
                        self.app.after(0, lambda: self.detection_indicator.configure(text="🔍 No pigs detected", text_color="gray"))
                    
                    # Update statistics display
                    self.app.after(0, self.update_stats_display)
                
                # Calculate FPS
                current_time = time.time()
                if current_time - self.last_frame_time > 0:
                    instantaneous_fps = 1.0 / (current_time - self.last_frame_time)
                    if current_time - self.fps_update_time >= 0.5:  # Update FPS display twice per second
                        self.current_fps = instantaneous_fps
                        self.app.after(0, lambda fps=self.current_fps: self.fps_indicator.configure(text=f"FPS: {fps:.1f}"))
                        self.fps_update_time = current_time
                self.last_frame_time = current_time
                
                # Convert frame for display
                img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img_pil = Image.fromarray(img_rgb)
                imgtk = ImageTk.PhotoImage(image=img_pil)
                
                # Update UI in main thread
                self.app.after(0, lambda img=imgtk: self.video_label.configure(image=img))
                self.app.after(0, lambda img=imgtk: setattr(self.video_label, 'image', img))
                
                # Adaptive sleeping to maintain reasonable frame rate
                elapsed = time.time() - loop_start
                if elapsed < 0.03:  # Target ~30 FPS
                    time.sleep(0.03 - elapsed)
                
            except Exception as e:
                self.log_message(f"❌ Error in detection loop: {str(e)}")
                time.sleep(0.1)

    def on_closing(self):
        """Clean up resources when closing the application"""
        self.app_running = False
        self.log_message("Shutting down system...")
        
        # Wait for detection thread to finish
        if self.detection_thread and self.detection_thread.is_alive():
            self.detection_thread.join(timeout=1.0)
        
        if self.capture is not None:
            self.capture.release()
        
        self.app.destroy()

    def run(self):
        """Run the application"""
        # Initialize the system
        initialization_result = self.initialize_system()

        # Start detection thread if initialization was successful
        if initialization_result:
            self.detection_thread = threading.Thread(target=self.detection_loop, daemon=True)
            self.detection_thread.start()
        else:
            self.log_message("⚠️ System initialization failed. Please check your settings and try again.")

        # Start the app
        self.app.mainloop()

if __name__ == "__main__":
    app = SwineDetectionSystem()
    app.run()
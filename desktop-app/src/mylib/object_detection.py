# src/mylib/mylib.py

import cv2
import os


def check_exist_file(file_path: str):
    """Check if a file exists."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file '{file_path}' does not exist.")

def read_class_names(file_path: str) -> list:
        check_exist_file(file_path)
        with open(file_path, 'r') as f:
            class_names = [line.strip() for line in f.readlines()]
        return class_names

def check_camera(cap):
    """Check if the camera is opened successfully."""
    if not cap.isOpened():
        raise TypeError("Cannot open camera.")

def track_objects(frame, boxes, class_list):
    predicted_obj = []
    count_cls = {"clean": 0, "uncleaned": 0, "dirt": 0, "total": 0}
    for indx, box in enumerate(boxes):
        x1, y1, x2, y2, conf_score, cls = box
        x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])
        conf_score_str = "%.2f" % conf_score
        cls_center_x = (x1 + x2) // 2
        cls_center_y = (y1 + y2) // 2
        cls_center_pnt = (cls_center_x, cls_center_y)
        cls_id = class_list[int(cls)]

        frame = display_object_info(frame, x1, y1, x2, y2, cls_id, conf_score, cls_center_pnt)

        predicted_obj.append(cls_id)

        if cls_id == "clean-pig":
            count_cls["clean"] += 1
        elif cls_id == "uncleaned-pig":
            count_cls["uncleaned"] += 1
        elif cls_id == "dirt":
            count_cls["dirt"] += 1

    count_cls["total"] = len(predicted_obj)

    return [frame, predicted_obj, count_cls]

def display_object_info(frame, x1, y1, x2, y2, cls_id, conf_score, cls_center_pnt):
    """Draw object information (bounding box, class, and confidence score) on the frame with aesthetic colors."""

    # Soft, aesthetic color mapping (BGR)
    color_map = {
        "clean-pig": (180, 238, 180),       # Soft mint green
        "uncleaned-pig": (200, 215, 255),   # Sky blue
        "dirt": (120, 150, 255),            # Coral rose
    }

    color = color_map.get(cls_id, (255, 255, 255))  # Default to white if unknown

    cv2.circle(img=frame, center=cls_center_pnt, radius=5, color=color, thickness=-1)
    cv2.rectangle(img=frame, pt1=(x1, y1), pt2=(x2, y2), color=color, thickness=2)
    text = f"{cls_id} {conf_score*100:.2f}%"
    cv2.putText(img=frame, text=text, org=(x1, y1 - 10 if y1 - 10 > 10 else y1 + 15),
                fontFace=cv2.FONT_HERSHEY_SIMPLEX, fontScale=0.75, color=color, thickness=2)
    
    return frame

def load_camera(video_source):
    """Load camera from video source."""
    captured = cv2.VideoCapture(video_source)
    check_camera(captured)
    return captured

def get_prediction_boxes(frame, yolo_model, confidence):
    """Get prediction boxes from the YOLO model."""
    pred = yolo_model.predict(source=[frame], save=False, conf=confidence)
    results = pred[0]
    boxes = results.boxes.data.numpy()
    return boxes

def show_frame(frame, frame_name, wait_key=1, ord_key='q'):
    """Display a frame using OpenCV."""
    cv2.imshow(frame_name, frame)
    if cv2.waitKey(wait_key) & 0xFF == ord(ord_key):
        return False
    return True

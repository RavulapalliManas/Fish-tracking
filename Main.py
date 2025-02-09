import cv2
import numpy as np
import argparse
import os
import sys
import json
from tqdm import tqdm
import csv  
import tkinter as tk
from tkinter import simpledialog
import pandas as pd
import multiprocessing as mp

class BoxManager:
    def __init__(self):
        self.boxes = [] 
        self.labels = []
        self.drawing = False
        self.current_box_start = None
        self.current_box_end = None
        self.selected_box_index = None
        self.selected_corner_index = None
        self.moving_box = False
        self.move_start = None

    def get_near_corner(self, box, point, threshold=10):
        """Return the index of the corner if point is within threshold; else None."""
        for i, corner in enumerate(box):
            if np.hypot(corner[0] - point[0], corner[1] - point[1]) < threshold:
                return i
        return None

    def point_in_box(self, point, box):
        """Return True if the point is inside the polygon defined by the box."""
        pts = np.array(box, np.int32).reshape((-1, 1, 2))
        return cv2.pointPolygonTest(pts, point, False) >= 0

    def handle_mouse_event(self, event, x, y, flags, param):
        point = (x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            for i, box in enumerate(self.boxes):
                corner_idx = self.get_near_corner(box, point)
                if corner_idx is not None:
                    self.selected_box_index = i
                    self.selected_corner_index = corner_idx
                    return
            for i, box in enumerate(self.boxes):
                if self.point_in_box(point, box):
                    self.selected_box_index = i
                    self.moving_box = True
                    self.move_start = point
                    return
            self.drawing = True
            self.current_box_start = point
            self.current_box_end = point

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing:
                self.current_box_end = point
            elif self.selected_corner_index is not None and self.selected_box_index is not None:
                self.boxes[self.selected_box_index][self.selected_corner_index] = point
            elif self.moving_box and self.selected_box_index is not None and self.move_start is not None:
                dx = x - self.move_start[0]
                dy = y - self.move_start[1]
                self.boxes[self.selected_box_index] = [
                    (cx + dx, cy + dy) for (cx, cy) in self.boxes[self.selected_box_index]
                ]
                self.move_start = point

        elif event == cv2.EVENT_LBUTTONUP:
            if self.drawing:
                self.drawing = False
                x1, y1 = self.current_box_start
                x2, y2 = self.current_box_end
                x_min, x_max = min(x1, x2), max(x1, x2)
                y_min, y_max = min(y1, y2), max(y1, y2)
                new_box = [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]
                self.boxes.append(new_box)
                self.labels.append(f"Box {len(self.boxes)}")
                self.current_box_start = None
                self.current_box_end = None
            self.selected_box_index = None
            self.selected_corner_index = None
            self.moving_box = False
            self.move_start = None

    def draw_boxes(self, frame):
        temp_frame = frame.copy()
        for i, box in enumerate(self.boxes):
            pts = np.array(box, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(temp_frame, [pts], isClosed=True, color=(0, 255, 0), thickness=2)
            if i < len(self.labels):
                cv2.putText(temp_frame, self.labels[i], (box[0][0], box[0][1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            for corner in box:
                cv2.circle(temp_frame, corner, radius=5, color=(0, 0, 255), thickness=-1)
        if self.drawing and self.current_box_start and self.current_box_end:
            cv2.rectangle(temp_frame, self.current_box_start, self.current_box_end, (255, 0, 0), 2)
        return temp_frame

    def remove_last_box(self):
        if self.boxes:
            self.boxes.pop()
            self.labels.pop()

    def get_box_data(self):
        return {label: {"coords": box, "time": 0} for label, box in zip(self.labels, self.boxes)}

    def save_configuration(self, filename):
        config = {"boxes": self.boxes, "labels": self.labels}
        with open(filename, 'w') as f:
            json.dump(config, f)

    def load_configuration(self, filename):
        with open(filename, 'r') as f:
            config = json.load(f)
            self.boxes = config["boxes"]
            self.labels = config["labels"]

    def handle_key_press(self, key):
        if key == ord('z'):
            self.remove_last_box()
        elif key == ord('r'):
            self.boxes = []
            self.labels = []
        elif key == ord('q'):
            print("Quit key pressed. Exiting...")
            sys.exit()  

def define_boxes(video_path, original_fps=30, slowed_fps=10, config_file=None):
    """
    Allows the user to interactively draw and modify boxes on the first frame of the video.
    
    Controls:
    - Draw a new box by dragging with the left mouse button.
    - Click near a box's corner (handle) to drag and reshape/rotate it.
    - Click inside a box (away from handles) to move the entire box.
    - 'z' to undo the last box.
    - 'r' to reset (remove) all boxes.
    - 's' to save configuration and exit.
    - 'q' to quit without saving.
    """
   
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    if not ret:
        print("Error: Cannot read the video.")
        cap.release()
        return {}

    box_manager = BoxManager()

    if config_file and os.path.exists(config_file):
        try:
            box_manager.load_configuration(config_file)
            print(f"Loaded existing box configuration from {config_file}")
        except Exception as e:
            print(f"Error loading configuration: {e}")

    window_name = "Draw Boxes"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, box_manager.handle_mouse_event)

    print("\nControls:")
    print("- Draw new box by dragging with the left mouse button")
    print("- Click near a corner to drag it (rotate/reshape the box)")
    print("- Click inside a box to move it entirely")
    print("- Press 'z' to undo last box")
    print("- Press 's' to save configuration and exit")
    print("- Press 'q' to quit without saving")
    print("- Press 'r' to reset all boxes")

    while True:
        display_frame = box_manager.draw_boxes(frame)
        instructions = "Draw/move/resize boxes | 'z': undo | 's': save | 'q': quit | 'r': reset"
        cv2.putText(display_frame, instructions, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.imshow(window_name, display_frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('s'):
            if config_file:
                try:
                    box_manager.save_configuration(config_file)
                    print(f"Saved box configuration to {config_file}")
                except Exception as e:
                    print(f"Error saving configuration: {e}")
            break
        elif key == ord('z'):
            box_manager.remove_last_box()
        elif key == ord('r'):
            box_manager.boxes = []
            box_manager.labels = []
        elif key == ord('q'):
            box_manager.boxes = []
            box_manager.labels = []
            break

    cv2.destroyWindow(window_name)
    cap.release()

    return box_manager.get_box_data()

def check_video_path(path):
    if not os.path.exists(path):
        print(f"Error: Video file not found at {path}")
        exit()

def initialize_video_capture(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print("Error: Could not open video file")
        exit()
    return cap

def preprocess_frame(frame, brightness_increase, clahe, scale_factor=0.5):
    if scale_factor != 1.0:
        frame = cv2.resize(frame, None, fx=scale_factor, fy=scale_factor)
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    gray = cv2.add(gray, brightness_increase)
    
    enhanced = clahe.apply(gray)
    
    return enhanced, scale_factor

def detect_fish(enhanced, fgbg, min_contour_area=10):
    """
    Detect fish in the given frame using background subtraction and contour detection.
    """
    fg_mask = fgbg.apply(enhanced)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    eroded_mask = cv2.erode(fg_mask, kernel, iterations=1)
    dilated_mask = cv2.dilate(eroded_mask, kernel, iterations=1)
    contours, _ = cv2.findContours(dilated_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [c for c in contours if cv2.contourArea(c) > min_contour_area]

def process_frame(frame, fgbg, clahe, brightness_increase, scale_factor):
    """
    Enhance the frame and detect fish contours.
    """
    # Convert to grayscale and apply CLAHE
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    enhanced = clahe.apply(gray)
    enhanced = cv2.convertScaleAbs(enhanced, alpha=1, beta=brightness_increase)

    # Resize frame for faster processing
    if scale_factor != 1.0:
        enhanced = cv2.resize(enhanced, None, fx=scale_factor, fy=scale_factor)

    # Detect fish
    contours = detect_fish(enhanced, fgbg)
    return enhanced, contours

def is_contour_in_box(contour, box):
    """
    Check if a given contour is inside a defined quadrilateral box.
    
    Args:
        contour: Contour points.
        box: A dictionary with box information, 
             where "coords" is a list of four corner tuples.
             
    Returns:
        True if the contour's center is within the box, False otherwise.
    """
    pts = np.array(box["coords"], dtype=np.int32).reshape((-1, 1, 2))
    x, y, w, h = cv2.boundingRect(contour)
    cx, cy = x + w / 2, y + h / 2
    return cv2.pointPolygonTest(pts, (cx, cy), False) >= 0

def draw_fish_contours(frame, contours, boxes, time_spent, fps, frame_skip):
    """
    Draw contours and update time spent in each box.
    """
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        # Check if the fish is within any defined box
        for i, box in enumerate(boxes):
            if box.contains(x, y, w, h):
                time_spent[i] += frame_skip / fps

def log_video_info(cap):
    print("Logging video information...")
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Video Width: {width}, Height: {height}, FPS: {fps}")

def handle_key_press(key):
    if key == ord('q'):
        print("Quit key pressed. Exiting...")
        sys.exit()  
    return False

def main():
    """
    Main function to process the video and track fish.
    """
    print("Starting video processing...")
    path = "/Users/manasvenkatasairavulapalli/Downloads/n2.mov"
    check_video_path(path)
    cap = initialize_video_capture(path)
    log_video_info(cap)

    box_manager = BoxManager()
    box_data = define_boxes(path)
    print("User-defined boxes:", box_data)

    # Processing parameters
    frame_skip = 2
    scale_factor = 0.7
    brightness_increase = 35
    contrast_clip_limit = 0.8
    min_contour_area = 15

    clahe = cv2.createCLAHE(clipLimit=contrast_clip_limit, tileGridSize=(8,8))
    fgbg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=30, detectShadows=False)

    frame_count = 0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    original_fps = cap.get(cv2.CAP_PROP_FPS)
    time_spent = [0] * len(box_data)

    pbar = tqdm(total=total_frames, desc="Processing Video", unit="frame", dynamic_ncols=True)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_skip != 0:
            frame_count += 1
            pbar.update(1)
            continue

        enhanced, contours = process_frame(frame, fgbg, clahe, brightness_increase, scale_factor)

        if scale_factor != 1.0:
            contours = [np.round(c / scale_factor).astype(np.int32) for c in contours]

        draw_fish_contours(enhanced, contours, list(box_data.values()), time_spent, original_fps, frame_skip)

        cv2.imshow("frame", enhanced)
        pbar.update(1)
        frame_count += 1

        key = cv2.waitKey(1) & 0xFF
        box_manager.handle_key_press(key)

    pbar.close()
    cap.release()
    cv2.destroyAllWindows()

    for i, (box_name, box_info) in enumerate(box_data.items()):
        box_info["time"] = time_spent[i]
        print(f"Time spent in {box_name}: {time_spent[i]:.2f} seconds")

    return box_data

if __name__ == "__main__":
    box_data = main()
    print("Returned box data:", box_data)


"""Visualization module: Generates rich annotated frames and HUD for the Web Dashboard."""

import io
import logging
from typing import List, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from computer_vision.schemas import DetectedObject, LaneObservation

logger = logging.getLogger(__name__)

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class Visualizer:
    """Renders computer vision annotations and telemetry HUD onto camera frames."""

    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height

    def annotate_frame(
        self,
        frame: Optional[np.ndarray],
        detections: List[DetectedObject],
        lane: Optional[LaneObservation] = None,
        state_text: str = "IDLE",
        goal_text: Optional[str] = None,
        is_blocked: bool = False,
        mode: str = "SIMULATION"
    ) -> bytes:
        """Annotates image frame and returns JPEG encoded bytes for web streaming."""
        if frame is None or frame.size == 0:
            # Generate a blank fallback frame with status message
            frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            frame[:] = (25, 25, 30) # Dark gray background

        # Work on a copy to avoid mutating source
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        if HAS_CV2:
            return self._annotate_cv2(annotated, detections, lane, state_text, goal_text, is_blocked, mode, w, h)
        else:
            return self._annotate_pil(annotated, detections, lane, state_text, goal_text, is_blocked, mode, w, h)

    def _annotate_cv2(
        self,
        img: np.ndarray,
        detections: List[DetectedObject],
        lane: Optional[LaneObservation],
        state_text: str,
        goal_text: Optional[str],
        is_blocked: bool,
        mode: str,
        w: int,
        h: int
    ) -> bytes:
        # 1. Draw Lane guidance if detected
        if lane and lane.detected:
            # Draw center guidance marker
            center_x = int(w / 2.0 - (lane.center_offset_normalized * (w / 2.0)))
            cv2.line(img, (int(w / 2.0), h - 30), (center_x, h - 90), (0, 255, 255), 2)
            cv2.circle(img, (center_x, h - 90), 6, (0, 255, 0), -1)

        # 2. Draw Object Bounding Boxes
        for det in detections:
            x1 = int(det.bbox.x1 * w)
            y1 = int(det.bbox.y1 * h)
            x2 = int(det.bbox.x2 * w)
            y2 = int(det.bbox.y2 * h)

            # Color: Red for obstacle, green/cyan for normal target
            box_color = (0, 0, 255) if det.is_obstacle else (0, 230, 115)
            cv2.rectangle(img, (x1, y1), (x2, y2), box_color, 2)

            # Label text
            dist_str = f" {det.estimated_distance_m:.1f}m" if det.estimated_distance_m else ""
            label_str = f"{det.label} ({int(det.confidence*100)}%){dist_str}"
            
            # Label background box
            cv2.rectangle(img, (x1, max(0, y1 - 22)), (x1 + len(label_str) * 9, y1), box_color, -1)
            cv2.putText(
                img, label_str, (x1 + 3, y1 - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA
            )

        # 3. Top HUD Banner
        # Semi-transparent overlay banner at top
        banner = img[0:40, 0:w].copy()
        cv2.rectangle(img, (0, 0), (w, 40), (20, 20, 25), -1)
        cv2.addWeighted(banner, 0.4, img[0:40, 0:w], 0.6, 0, img[0:40, 0:w])

        # State badge
        state_color = (0, 255, 0) if state_text == "NAVIGATING" else (0, 165, 255)
        if is_blocked:
            state_color = (0, 0, 255)
            state_text = "BLOCKED"

        cv2.putText(img, f"STATE: {state_text}", (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, state_color, 2)
        
        mode_str = f"[{mode}]"
        cv2.putText(img, mode_str, (w - 120, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (200, 200, 200), 1)

        if goal_text:
            goal_disp = f"Goal: {goal_text[:25]}"
            cv2.putText(img, goal_disp, (180, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1)

        # Encode to JPEG
        _, jpeg_buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return jpeg_buf.tobytes()

    def _annotate_pil(
        self,
        img_array: np.ndarray,
        detections: List[DetectedObject],
        lane: Optional[LaneObservation],
        state_text: str,
        goal_text: Optional[str],
        is_blocked: bool,
        mode: str,
        w: int,
        h: int
    ) -> bytes:
        """Pillow rendering fallback."""
        # Convert BGR array to RGB PIL Image
        rgb_array = img_array[:, :, ::-1] if img_array.ndim == 3 else img_array
        pil_img = Image.fromarray(rgb_array)
        draw = ImageDraw.Draw(pil_img)

        # Draw detections
        for det in detections:
            x1 = int(det.bbox.x1 * w)
            y1 = int(det.bbox.y1 * h)
            x2 = int(det.bbox.x2 * w)
            y2 = int(det.bbox.y2 * h)
            outline = (255, 50, 50) if det.is_obstacle else (50, 230, 100)
            draw.rectangle([x1, y1, x2, y2], outline=outline, width=2)
            dist_str = f" {det.estimated_distance_m:.1f}m" if det.estimated_distance_m else ""
            label_str = f"{det.label} ({int(det.confidence*100)}%){dist_str}"
            draw.text((x1 + 3, max(0, y1 - 15)), label_str, fill=outline)

        # Top banner
        draw.rectangle([0, 0, w, 35], fill=(30, 30, 35))
        state_color = (255, 50, 50) if is_blocked else (50, 255, 50) if state_text == "NAVIGATING" else (255, 200, 50)
        draw.text((15, 10), f"STATE: {state_text}", fill=state_color)
        if goal_text:
            draw.text((180, 10), f"Goal: {goal_text}", fill=(240, 240, 240))
        draw.text((w - 110, 10), f"[{mode}]", fill=(180, 180, 180))

        # Lane
        if lane and lane.detected:
            cx = int(w / 2.0 - (lane.center_offset_normalized * (w / 2.0)))
            draw.line([(int(w / 2.0), h - 20), (cx, h - 70)], fill=(255, 255, 0), width=3)

        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()

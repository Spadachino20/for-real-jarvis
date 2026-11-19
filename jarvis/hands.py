"""Hand gestures from the webcam, trained on YOUR hands (MediaPipe landmarks + nearest neighbours).

  python -m jarvis.hands      test window; train it there: hold a gesture and press its number (records 3 s)

The camera can look from anywhere (even down at the keyboard): you record each gesture from your own
angle, plus "0 = nada" while you type, so typing is a class of its own and never fires anything.
A gesture counts only when held still ~1 s. Swipes are trained too (5 right, 6 left): the last 0.6 s of the
hand's path plus its shape, against your recorded swipes AND your typing (0), so typing moves don't count.
"""
from __future__ import annotations

import time
import numpy as np

from . import settings

SAMPLES = settings.DATA / "gestures.npz"
SWIPES = settings.DATA / "swipes.npz"
CAMERA_OFF = settings.DATA / "camera-off"  # exists = eyes closed ("apagá la cámara")
WINDOW, STEPS, MIN_DX = 0.6, 8, 0.12  # a swipe: 0.6 s of path, moving at least 12% of the picture sideways
HOLD_SEC = 1.0
QUICK = {"puño": 0.4}  # stopping him shouldn't wait a whole second
CLASSES = {ord("0"): "nada", ord("1"): "puño", ord("2"): "palma", ord("4"): "pulgar arriba",
           ord("5"): "barrer derecha", ord("6"): "barrer izquierda", ord("7"): "cuernos"}
# moving gestures: (axis 0 = x / 1 = y, sign). In the picture y grows downward.
MOVES = {"barrer derecha": (0, 1), "barrer izquierda": (0, -1)}


def landmarker():
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    return vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(settings.ROOT / "models" / "hand_landmarker.task")),
        running_mode=vision.RunningMode.VIDEO, num_hands=2,
        min_hand_detection_confidence=0.5, min_tracking_confidence=0.5)), mp


def features(hand, left: bool) -> np.ndarray:
    """21 points relative to the wrist, scaled to the hand's size; left hands mirrored so one sample serves both."""
    p = np.array([[q.x, q.y] for q in hand])
    p -= p[0]
    if left:
        p[:, 0] = -p[:, 0]
    return (p / (np.abs(p).max() or 1)).ravel()


class Classifier:
    def __init__(self, path=SAMPLES, dims: int = 42) -> None:
        self.path, self.x, self.y = path, np.zeros((0, dims)), np.array([], dtype=object)
        if path.exists():
            d = np.load(path, allow_pickle=True)
            self.x, self.y = d["x"], d["y"]

    def add(self, f: np.ndarray, label: str) -> None:
        self.x, self.y = np.vstack([self.x, f]), np.append(self.y, label)

    def save(self) -> None:
        np.savez(self.path, x=self.x, y=self.y)

    def predict(self, f: np.ndarray, k: int = 7) -> tuple[str | None, float]:
        if len(self.y) < k:
            return None, 0.0
        near = self.y[np.argsort(((self.x - f) ** 2).sum(1))[:k]]
        labels, votes = np.unique(near, return_counts=True)
        return labels[votes.argmax()], votes.max() / k


class Hold:
    """Fires once when the same gesture stays HOLD_SEC with the hand still."""

    def __init__(self) -> None:
        self.name, self.since, self.fired, self.pos = None, 0.0, False, None
        self.last = (None, -9.0)

    def feed(self, name: str | None, pos: tuple[float, float] | None, now: float) -> str | None:
        moved = pos and self.pos and abs(pos[0] - self.pos[0]) + abs(pos[1] - self.pos[1]) > 0.08
        if name != self.name or moved:
            self.name, self.since, self.fired, self.pos = name, now, False, pos
            return None
        if name and not self.fired and now - self.since >= QUICK.get(name, HOLD_SEC):
            self.fired = True
            if self.last[0] == name and now - self.last[1] < 1.5:
                return None  # the other hand (or a twitch) repeating the same gesture
            self.last = (name, now)
            return name
        return None


class Sweeps:
    """Swipes from the hand's recent path. feed() also records while you train (label = what you're recording)."""

    def __init__(self) -> None:
        self.clf, self.tracks, self.quiet_until = Classifier(SWIPES, STEPS * 2 + 42), {}, 0.0

    def feed(self, side: str, x: float, y: float, pose: np.ndarray, now: float, recording: str | None = None) -> str | None:
        track = self.tracks.setdefault(side, [])
        track.append((now, x, y))
        while track and now - track[0][0] > WINDOW:
            track.pop(0)
        if len(track) < 4 or now - track[0][0] < WINDOW * 0.8:
            return None
        ts, xs, ys = np.array(track).T
        at = np.linspace(ts[0], now, STEPS)
        d = (xs[-1] - xs[0], ys[-1] - ys[0])

        def along(label: str) -> bool:  # moving the way that gesture moves (the stroke, not the way back)
            axis, sign = MOVES[label]
            return abs(d[axis]) > MIN_DX and abs(d[axis]) > abs(d[1 - axis]) and (d[axis] > 0) == (sign > 0)
        f = np.concatenate([3 * (np.interp(at, ts, xs) - xs[0]), 3 * (np.interp(at, ts, ys) - ys[0]), 0.5 * pose])
        if recording == "nada" or (recording in MOVES and along(recording)):
            self.clf.add(f, recording)
            return None
        if recording or max(abs(d[0]), abs(d[1])) < MIN_DX or now < self.quiet_until:
            return None
        label, c = self.clf.predict(f)
        if label in MOVES and c >= 0.85 and along(label):
            self.tracks.clear()
            self.quiet_until = now + 1.0
            return label
        return None


def watch(on_gesture, camera: int = 0) -> None:
    """JARVIS's eyes: no window, ~12 frames a second, calls on_gesture("puño") etc. Blocks: run it in a thread."""
    import cv2
    if not SAMPLES.exists():
        print("gestures: not trained yet (python -m jarvis.hands)")
        return
    det, mp = landmarker()
    clf, hold, sweeps, t0 = Classifier(), Hold(), Sweeps(), time.time()
    while True:
        while CAMERA_OFF.exists():
            time.sleep(1)
        cam = cv2.VideoCapture(camera, cv2.CAP_DSHOW)
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
        while not CAMERA_OFF.exists() and (ok := cam.read())[0]:
            frame, now = cv2.flip(ok[1], 1), time.time()
            r = det.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
                                     int((now - t0) * 1000))
            name, pos, conf = None, None, 0.0
            swiped = None
            for hand, side in zip(r.hand_landmarks, r.handedness):
                f = features(hand, side[0].category_name == "Left")
                label, c = clf.predict(f)
                if label and label != "nada" and c >= 0.85 and c > conf:
                    name, pos, conf = label, (hand[0].x, hand[0].y), c
                swiped = sweeps.feed(side[0].category_name, hand[0].x, hand[0].y, f, now) or swiped
            if fired := swiped or hold.feed(name, pos, now):
                print(time.strftime("%H:%M:%S"), "gesture:", fired)
                try:
                    on_gesture(fired)
                except Exception as e:  # noqa: BLE001
                    print("gesture action failed:", e)
            time.sleep(max(0.0, 0.08 - (time.time() - now)))
        cam.release()
        if CAMERA_OFF.exists():
            continue
        time.sleep(5)  # camera busy (a video call?) or unplugged: try again


def test_window(camera: int = 0) -> None:
    import cv2
    det, mp = landmarker()
    clf, hold, sweeps = Classifier(), Hold(), Sweeps()
    cam = cv2.VideoCapture(camera, cv2.CAP_DSHOW)
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
    last, rec, t0 = ("", 0.0), (None, 0.0), time.time()
    print("0 nada (escribir) | 1 puño | 2 palma | 4 pulgar arriba | 5 barrer der | 6 barrer izq | 7 cuernos | Esc salir", flush=True)
    while True:
        ok, frame = cam.read()
        if not ok:
            print("No veo la cámara.", flush=True)
            break
        frame = cv2.flip(frame, 1)  # a mirror: your right is the picture's right
        now = time.time()
        r = det.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
                                 int((now - t0) * 1000))
        name, pos, conf, swiped = None, None, 0.0, None
        recording = rec[0] if rec[0] and now < rec[1] else None
        for hand, side in zip(r.hand_landmarks, r.handedness):
            for p in hand:
                cv2.circle(frame, (int(p.x * frame.shape[1]), int(p.y * frame.shape[0])), 3, (255, 200, 0), -1)
            f = features(hand, side[0].category_name == "Left")
            if recording and recording not in MOVES:
                clf.add(f, recording)
            swiped = sweeps.feed(side[0].category_name, hand[0].x, hand[0].y, f, now, recording) or swiped
            label, c = clf.predict(f)
            if label and label != "nada" and c >= 0.85 and c > conf:  # sure votes only: a typing hand sits between classes
                name, pos, conf = label, (hand[0].x, hand[0].y), c
        if rec[0] and now >= rec[1]:
            clf.save()
            sweeps.clf.save()
            n = (clf.y == rec[0]).sum() + (sweeps.clf.y == rec[0]).sum()
            print(f"grabado: {rec[0]} ({n} muestras)", flush=True)
            rec = (None, 0.0)
        fired = swiped or hold.feed(name, pos, now)
        if fired:
            last = (fired, now)
            print(time.strftime("%H:%M:%S"), "GESTO:", fired, flush=True)
        held = now - hold.since if hold.name else 0
        top = f"GRABANDO {rec[0]} {rec[1] - now:.1f}s" if rec[0] else f"{name or '-'}  {min(held, HOLD_SEC):.1f}s"
        cv2.putText(frame, top, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255) if rec[0] else (255, 255, 255), 2)
        if now - last[1] < 1.5:
            cv2.putText(frame, f"GESTO: {last[0]}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 0), 3)
        counts = " ".join(f"{k}:{(clf.y == v).sum() + (sweeps.clf.y == v).sum()}" for k, v in zip("01234567", CLASSES.values()))
        cv2.putText(frame, "0 nada 1 puno 2 palma 3 V 4 ok 5 der 6 izq 7 rock | " + counts, (10, frame.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        cv2.imshow("JARVIS - manos (Esc para salir)", frame)
        key = cv2.waitKey(1)
        if key == 27:
            break
        if key in CLASSES and not rec[0]:
            rec = (CLASSES[key], now + 3)
    cam.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    h = Hold()
    assert h.feed("palma", (0.5, 0.5), 0) is None and h.feed("palma", (0.5, 0.5), 1.1) == "palma"
    assert h.feed("palma", (0.5, 0.5), 2) is None  # once per hold
    assert h.feed("palma", (0.7, 0.5), 3) is None  # moving (typing) resets it
    assert h.feed("palma", (0.7, 0.5), 4.1) == "palma"  # held again later: fires
    assert h.feed("palma", (0.2, 0.5), 4.2) is None and h.feed("palma", (0.2, 0.5), 5.3) is None  # other hand, <1.5 s: no
    c = Classifier.__new__(Classifier)
    c.x, c.y = np.vstack([np.zeros((7, 42)), np.ones((7, 42))]), np.array(["nada"] * 7 + ["puño"] * 7, dtype=object)
    assert c.predict(np.ones(42) * 0.9)[0] == "puño"
    s = Sweeps.__new__(Sweeps)
    s.clf, s.tracks, s.quiet_until = Classifier.__new__(Classifier), {}, 0.0
    s.clf.x, s.clf.y = np.zeros((0, STEPS * 2 + 42)), np.array([], dtype=object)
    for i in range(10):  # record a right sweep: the stroke is saved
        s.feed("Right", 0.2 + 0.05 * i, 0.5, np.zeros(42), i * 0.08, "barrer derecha")
    assert len(s.clf.y) > 0 and set(s.clf.y) == {"barrer derecha"}
    if "--test" not in __import__("sys").argv:
        test_window()

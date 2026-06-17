"""
Main renderer — assembles all scene frames into final MP4.
Handles: frame encoding, audio sync, BGM mixing, transitions.
"""
import subprocess, json, os, shutil
import numpy as np
from pathlib import Path
from config import W, H, FPS, FRAME_DIR, AUDIO_DIR, VIDEO_DIR

def frames_to_video(frames: list, out_path: str, fps: int = FPS) -> str:
    """Encode BGR numpy frames → mp4 using ffmpeg pipe."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg","-y","-loglevel","error",
        "-f","rawvideo","-vcodec","rawvideo",
        "-s",f"{W}x{H}","-pix_fmt","bgr24",
        "-r",str(fps),"-i","pipe:0",
        "-c:v","libx264","-preset","veryfast","-crf","20",
        "-pix_fmt","yuv420p",str(out)
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for frame in frames:
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg frame encode failed")
    return str(out)


def add_transition(frames_a: list, frames_b: list, transition: str, n: int = 12) -> list:
    """Blend end of scene A with start of scene B."""
    if transition == "fade" and len(frames_a) >= n and len(frames_b) >= n:
        blended = []
        for i in range(n):
            t = i / n
            f = (frames_a[-n+i] * (1-t) + frames_b[i] * t).astype(np.uint8)
            blended.append(f)
        return frames_a[:-n] + blended + frames_b[n:]
    elif transition == "zoom_cut":
        # No blend, hard cut
        return frames_a + frames_b
    else:
        return frames_a + frames_b


def render_full_video(
    storyboard      : list,
    narration_audio : str,
    bgm_audio       : str,
    out_video       : str,
    bg_images       : dict = None,
) -> str:
    """
    Full pipeline:
    1. Render each scene's frames
    2. Apply transitions
    3. Encode to raw video
    4. Mix narration + BGM
    5. Output final MP4
    """
    from visual_renderer import render_scene

    print(f"Rendering {len(storyboard)} scenes...")
    all_frames = []

    for i, scene in enumerate(storyboard):
        bg_path = None
        if bg_images:
            bg_path = bg_images.get(scene["scene_id"]) or bg_images.get("default")

        print(f"  Scene {scene['scene_id']:3d}/{len(storyboard)} | "
              f"{scene['visual']['type']:10} | {scene['duration']:.1f}s | "
              f"{scene['narration'][:40]}...", flush=True)

        scene_frames = render_scene(scene, bg_path)

        # Apply transition between scenes
        if all_frames and scene_frames:
            trans = scene.get("visual",{}).get("transition","cut")
            all_frames = add_transition(all_frames, scene_frames, trans, n=8)
        else:
            all_frames.extend(scene_frames)

    print(f"Total frames: {len(all_frames)} ({len(all_frames)/FPS:.1f}s)")

    # Encode video-only track
    raw_video = str(Path(VIDEO_DIR) / "raw_video.mp4")
    frames_to_video(all_frames, raw_video)
    print(f"Raw video: {raw_video}")

    # Mix audio: narration + BGM
    if Path(narration_audio).exists():
        _mix_audio(raw_video, narration_audio, bgm_audio, out_video)
    else:
        shutil.copy(raw_video, out_video)

    print(f"✅ Final video: {out_video} ({Path(out_video).stat().st_size//1024//1024}MB)")
    return out_video


def _mix_audio(video: str, narration: str, bgm: str, out: str):
    """Mix narration + BGM under video."""
    if bgm and Path(bgm).exists():
        total_dur = _get_dur(video)
        filter_cx = (
            "[1:a]volume=1.0[v];"
            f"[2:a]volume=0.08,aloop=loop=-1:size=2e+09,atrim=0:{total_dur:.2f}[bgm];"
            "[v][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        cmd = [
            "ffmpeg","-y","-loglevel","error",
            "-i",video,"-i",narration,"-i",bgm,
            "-filter_complex",filter_cx,
            "-map","0:v","-map","[aout]",
            "-c:v","copy","-c:a","aac","-b:a","192k",out
        ]
    else:
        cmd = [
            "ffmpeg","-y","-loglevel","error",
            "-i",video,"-i",narration,
            "-map","0:v","-map","1:a",
            "-c:v","copy","-c:a","aac","-b:a","192k",
            "-shortest",out
        ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        shutil.copy(video, out)

def _get_dur(p):
    r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                        "-of","default=noprint_wrappers=1:nokey=1",p],
                       capture_output=True,text=True)
    try: return float(r.stdout.strip())
    except: return 60.0

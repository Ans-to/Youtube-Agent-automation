#!/usr/bin/env python3
"""Dependency-light device profiling for adaptive, sequential video production."""
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_AUTO_DISK = object()


def _memory_total_bytes():
    """Return physical RAM bytes when detectable, otherwise None."""
    if sys.platform == "win32":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
        except Exception:
            return None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page_size > 0:
            return int(pages * page_size)
    except (AttributeError, OSError, ValueError):
        pass
    return None


def _detect_gpu():
    """Detect common dedicated GPUs without requiring optional packages."""
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                first = result.stdout.strip().splitlines()[0]
                parts = [part.strip() for part in first.split(",", 1)]
                memory_mib = None
                if len(parts) > 1:
                    try:
                        memory_mib = int(parts[1])
                    except ValueError:
                        pass
                return {
                    "detected": True,
                    "name": parts[0],
                    "dedicated_memory_bytes": memory_mib * 1024 * 1024 if memory_mib else None,
                    "detection_method": "nvidia-smi",
                }
        except (OSError, subprocess.TimeoutExpired):
            pass
    if sys.platform == "win32":
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell:
            script = (
                "Get-CimInstance Win32_VideoController | "
                "Select-Object -First 1 -Property Name,AdapterRAM | ConvertTo-Json -Compress"
            )
            try:
                result = subprocess.run(
                    [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                    capture_output=True, text=True, timeout=4, check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    item = json.loads(result.stdout)
                    if isinstance(item, dict):
                        name = str(item.get("Name") or "Unknown adapter")
                        ram = item.get("AdapterRAM")
                        try:
                            ram = int(ram) if ram is not None else None
                        except (TypeError, ValueError):
                            ram = None
                        return {
                            "detected": True,
                            "name": name,
                            "dedicated_memory_bytes": ram if ram and ram > 0 else None,
                            "detection_method": "Windows CIM",
                        }
            except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
                pass
    return {
        "detected": False,
        "name": None,
        "dedicated_memory_bytes": None,
        "detection_method": "no supported dedicated-GPU probe succeeded",
    }


def profile_device(base_path=None, cpu_count=None, total_memory_bytes=None, gpu=None, free_disk_bytes=_AUTO_DISK):
    """Return a stable, JSON-safe capability profile; arguments allow deterministic tests."""
    cpu_count = max(1, int(cpu_count if cpu_count is not None else (os.cpu_count() or 1)))
    total_memory_bytes = _memory_total_bytes() if total_memory_bytes is None else int(total_memory_bytes)
    gpu = _detect_gpu() if gpu is None else dict(gpu)
    base_path = Path(base_path or Path.cwd()).expanduser()
    if free_disk_bytes is _AUTO_DISK:
        try:
            free_disk_bytes = shutil.disk_usage(base_path).free
        except OSError:
            free_disk_bytes = None

    ram_gib = round(total_memory_bytes / (1024 ** 3), 2) if total_memory_bytes else None
    gpu_memory = gpu.get("dedicated_memory_bytes")
    dedicated_gpu_gib = round(gpu_memory / (1024 ** 3), 2) if gpu_memory else None
    if ram_gib is not None and ram_gib < 12:
        tier = "cpu_constrained"
        reason = "Less than 12 GiB RAM detected; prioritize small batches and CPU-safe settings."
    elif gpu.get("detected") and dedicated_gpu_gib is not None and dedicated_gpu_gib >= 6 and ram_gib is not None and ram_gib >= 16:
        tier = "gpu_accelerated"
        reason = "Dedicated GPU memory and system RAM meet the accelerated profile threshold."
    else:
        tier = "balanced"
        reason = "Use conservative sequential processing; no compatible high-memory dedicated GPU was confirmed."

    render_threads = max(1, min(cpu_count - 1 if cpu_count > 1 else 1, 4 if tier == "cpu_constrained" else 8))
    return {
        "schema_version": 1,
        "platform": platform.system().lower() or sys.platform,
        "cpu_count": cpu_count,
        "total_memory_bytes": total_memory_bytes,
        "ram_gib": ram_gib,
        "gpu": gpu,
        "dedicated_gpu_memory_gib": dedicated_gpu_gib,
        "free_disk_bytes": int(free_disk_bytes) if free_disk_bytes is not None else None,
        "tier": tier,
        "render_threads": render_threads,
        "max_parallel_heavy_jobs": 1,
        "preserve_requested_output_quality": True,
        "automatic_resolution_downgrade": False,
        "reason": reason,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the profile as JSON.")
    parser.add_argument("--path", default=".", help="Path used to estimate free disk space.")
    args = parser.parse_args()
    profile = profile_device(args.path)
    if args.json:
        print(json.dumps(profile, indent=2))
    else:
        print("Device capability profile")
        print("Tier:", profile["tier"])
        print("RAM GiB:", profile["ram_gib"] if profile["ram_gib"] is not None else "unknown")
        print("CPU threads for encoding:", profile["render_threads"])
        print("GPU:", profile["gpu"].get("name") or "not detected")
        print("Heavy jobs at once:", profile["max_parallel_heavy_jobs"])
        print("Quality downgrade automatic:", profile["automatic_resolution_downgrade"])
        print("Reason:", profile["reason"])


if __name__ == "__main__":
    main()

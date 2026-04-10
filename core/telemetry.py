import psutil

def get_system_metrics():
    """Fetches real-time CPU and RAM usage."""
    # psutil.cpu_percent needs to be called once, then again to get a delta.
    # Passing interval=0.1 gives a quick, relatively accurate reading without blocking too long.
    cpu_usage = psutil.cpu_percent(interval=0.1)
    
    # Get RAM usage
    ram = psutil.virtual_memory()
    ram_usage = ram.percent
    ram_used_gb = ram.used / (1024 ** 3)
    ram_total_gb = ram.total / (1024 ** 3)
    
    # Get Disk usage (for the root WSL drive)
    disk = psutil.disk_usage('/')
    disk_usage = disk.percent

    return {
        "cpu": cpu_usage,
        "ram_percent": ram_usage,
        "ram_used": round(ram_used_gb, 1),
        "ram_total": round(ram_total_gb, 1),
        "disk": disk_usage
    }

if __name__ == "__main__":
    # Test it out
    metrics = get_system_metrics()
    print(f"CPU: {metrics['cpu']}% | RAM: {metrics['ram_used']}/{metrics['ram_total']} GB ({metrics['ram_percent']}%) | Disk: {metrics['disk']}%")
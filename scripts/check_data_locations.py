# scripts/check_data_locations.py
import os
import glob

def check_data_locations():
    """Check where data files are stored"""
    print("📁 DATA STORAGE LOCATIONS")
    print("=" * 50)
    
    # Check data directory
    data_dir = 'data'
    if os.path.exists(data_dir):
        print(f"📂 Data directory: {os.path.abspath(data_dir)}")
        files = glob.glob(os.path.join(data_dir, '*'))
        if files:
            print("📄 Files found:")
            for file in files:
                size = os.path.getsize(file)
                print(f"   {os.path.basename(file)} ({size} bytes)")
        else:
            print("   No data files yet")
    else:
        print("❌ Data directory doesn't exist yet")
    
    # Check for memory files
    memory_files = glob.glob('*.pkl') + glob.glob('data/*.pkl')
    if memory_files:
        print(f"\n💾 Memory files:")
        for file in memory_files:
            size = os.path.getsize(file)
            print(f"   {file} ({size} bytes)")
    
    # Check for CSV exports
    csv_files = glob.glob('data/*.csv')
    if csv_files:
        print(f"\n📊 CSV exports:")
        for file in csv_files:
            size = os.path.getsize(file)
            print(f"   {file} ({size} bytes)")

if __name__ == "__main__":
    check_data_locations()
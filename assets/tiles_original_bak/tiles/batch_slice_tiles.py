import os
import glob
from PIL import Image

def batch_slice_directory():
    """
    Scans the local directory for all images, slices them using an 8x4 grid 
    factoring in a 1-pixel spacing gap, and exports assets to 'sliced_output'.
    """
    # Grid specification targets
    GRID_WIDTH = 8
    GRID_HEIGHT = 4
    GAP = 1
    
    # Static mathematical dimensions for a 1408x768 sheet
    TILE_W = 175  
    TILE_H = 191  
    
    # Target output folder directory
    OUTPUT_ROOT = "sliced_output"
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    
    # Extensions matching common web/engine image configurations
    VALID_EXTENSIONS = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"]
    image_files = []
    
    for ext in VALID_EXTENSIONS:
        # Match case-insensitively across local folder rows
        image_files.extend(glob.glob(ext))
        image_files.extend(glob.glob(ext.upper()))
        
    # De-duplicate files list cleanly
    image_files = sorted(list(set(image_files)))
    
    if not image_files:
        print("[!] No matching source images found in the execution folder directory.")
        return

    print(f"[*] Found {len(image_files)} source files for slicing pipeline. Starting processing loop...")

    for master_file in image_files:
        # Prevent the script from processing files inside its own output targets
        if master_file.startswith(OUTPUT_ROOT):
            continue
            
        base_name = os.path.splitext(os.path.basename(master_file))[0]
        # Create a dedicated clean sub-folder container for this specific asset sheet group
        file_output_dir = os.path.join(OUTPUT_ROOT, f"{base_name}_sliced")
        os.makedirs(file_output_dir, exist_ok=True)
        
        print(f"\n[Slicing] Processing master target: '{master_file}'...")
        
        try:
            with Image.open(master_file) as master_img:
                img_w, img_h = master_img.size
                
                # Dynamic logging confirmation checks
                if img_w != 1408 or img_h != 768:
                    print(f"  -> Notice: File dimensions ({img_w}x{img_h}) mismatch standard 1408x768 specs. Clipping frames strictly to grid index coordinates.")
                
                tile_counter = 0
                
                # Run coordinate layout sweeps sequentially
                for row in range(GRID_HEIGHT):
                    for col in range(GRID_WIDTH):
                        # x_start = column * (width + gap)
                        x_start = col * (TILE_W + GAP)
                        y_start = row * (TILE_H + GAP)
                        
                        x_end = x_start + TILE_W
                        y_end = y_start + TILE_H
                        
                        # Guard bounding boxes from reading pixels completely off-canvas
                        if x_end <= img_w and y_end <= img_h:
                            tile_box = (x_start, y_start, x_end, y_end)
                            tile_crop = master_img.crop(tile_box)
                            
                            # Construct highly organized cell layout file paths
                            tile_filename = f"{base_name}_tile_r{row}_c{col}.png"
                            tile_filepath = os.path.join(file_output_dir, tile_filename)
                            
                            tile_crop.save(tile_filepath, "PNG")
                            tile_counter += 1
                            
                print(f"  -> [SUCCESS] Exported {tile_counter} seamless tile blocks into: '{file_output_dir}/'")
                
        except Exception as e:
            print(f"  -> [ERROR] Processing collapsed on file '{master_file}': {e}")

    print("\n[🏁 PIPELINE COMPLETE] All images processed cleanly. Master source files left fully intact.")

if __name__ == "__main__":
    batch_slice_directory()
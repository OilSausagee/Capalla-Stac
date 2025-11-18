# pip install leafmap rio-cogeo
# 檔名: convert_cog.py
import os
import glob
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
import rasterio

# --- 參數 ---
# (!!!) 確保路徑正確 (!!!)
SOURCE_DIR = "D:\\Capalla_data\\tif_file"
COG_DIR = "D:\\Capalla_data\\cog_files"
# -----------

os.makedirs(COG_DIR, exist_ok=True)
tif_files = glob.glob(os.path.join(SOURCE_DIR, "*.tif"))

print(f"開始轉換 {len(tif_files)} 個檔案到 COG...")

for tif_path in tif_files:
    filename = os.path.basename(tif_path)
    
    # (!!!) 跳過 SLC 檔案 (它們沒有 CRS，無法轉換)
    if "SLC" in filename:
        print(f"[跳過] {filename} (SLC 檔案)")
        continue
        
    out_path = os.path.join(COG_DIR, filename)
    
    if os.path.exists(out_path):
        print(f"[跳過] {filename} (COG 已存在)")
        continue

    try:
        print(f"  轉換中: {filename} ...")
        # 轉換 TIF 為 COG
        cog_translate(
            tif_path,
            out_path,
            cog_profiles.get("deflate") # 使用壓縮
        )
    except rasterio.errors.RasterioIOError as e:
        print(f"[錯誤] 無法轉換 {filename} (可能是 SLC 或無 CRS): {e}")
    except Exception as e:
        print(f"[錯誤] {filename}: {e}")

print("✅ COG 轉換完成！")
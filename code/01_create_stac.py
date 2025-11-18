import os
import glob
from datetime import datetime
import pystac
import rasterio
import rasterio.warp
from shapely.geometry import box, mapping

# ==== 1. 參數設定 ====

# (!!!) 請確保路徑正確 (!!!)
# 你的 TIF 影像所在的資料夾 (根據你的 log，它在這裡)
IMAGE_DIR = "D:\\Capalla_data\\cog_files" 
# 你要產生的 STAC 目錄的根資料夾
ROOT_DIR = "D:\\Capalla_data\\stac"
# 你的 Catalog 和 Collection ID
CATALOG_ID = "capella-custom-catalog"
COLLECTION_ID = "capella-local-imagery"
COLLECTION_DESCRIPTION = "這是我自己蒐集的 Capella 本地衛星影像"
LICENSE = "proprietary" # Capella 影像是商業的，用 "proprietary" (專有)


# ==== 2. 輔助函數 (v3 版 - 合併) ====

def get_stac_info_from_tif(tif_path):
    """
    (!!! v3 修正 !!!)
    開啟 TIF 檔案一次，並提取所有需要的 STAC 中繼資料：
    1. ID (from filename)
    2. Datetime (優先 from TIFFTAG_DATETIME, 備案 from filename)
    3. BBox (WGS 84)
    4. Geometry (WGS 84)
    
    返回: (item_id, item_datetime, bbox_wgs84, geom_wgs84)
    如果 TIF 無效 (如 SLC)，則返回 (None, None, None, None)
    """
    
    filename = os.path.basename(tif_path)
    item_id = os.path.splitext(filename)[0]
    item_datetime = None
    
    with rasterio.open(tif_path) as src:
        # --- A. 檢查 CRS (SCL 檔案) ---
        src_crs = src.crs
        if src_crs is None:
            print(f"  [跳過] {filename} 沒有 CRS (座標系統)，"
                  "可能是 SLC 原始資料，無法加入 STAC。")
            return None, None, None, None # 回傳四個 None
        
        # --- B. 提取地理資訊 (同 v2) ---
        bounds = src.bounds
        bbox_geom = box(bounds.left, bounds.bottom, bounds.right, bounds.top)
        
        if src_crs != "EPSG:4326":
            bbox_wgs84 = rasterio.warp.transform_bounds(
                src_crs, "EPSG:4326", *bounds
            )
            geom_wgs84 = rasterio.warp.transform_geom(
                src_crs, "EPSG:4326", mapping(bbox_geom)
            )
        else:
            bbox_wgs84 = bounds
            geom_wgs84 = mapping(bbox_geom)
        
        # --- C. (v3 新增) 優先從 TIF Tag 讀取時間 ---
        try:
            tags = src.tags()
            # 嘗試 'TIFFTAG_DATETIME' 或 'DATETIME' (標準名稱)
            datetime_str = tags.get('TIFFTAG_DATETIME') or tags.get('DATETIME')
            
            if datetime_str:
                # TIF Tag 標準格式通常是 'YYYY:MM:DD HH:MM:SS'
                item_datetime = datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S')
                print(f"    -> 成功從 TIF Tag 讀取時間: {item_datetime}")
        except Exception as e:
            print(f"  [警告] 嘗試從 TIF Tag 讀取 {filename} 時間失敗: {e}。將嘗試檔名解析...")
            item_datetime = None # 確保失敗時為 None, 進入備案

    # --- D. (v2 備案) 如果 TIF Tag 失敗，才嘗試從檔名解析 ---
    if item_datetime is None: # 只有在 item_datetime 還是 None 時才執行
        try:
            parts = item_id.split('_')
            timestamp_str = ""
            if parts[-1] == "preview":
                timestamp_str = parts[-3] # '..._preview.tif'
            else:
                timestamp_str = parts[-2] # '..._xxxx.tif'
            
            item_datetime = datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')
            print(f"    -> (備案) 成功從 Filename 讀取時間: {item_datetime}")
        
        except Exception as e:
            print(f"  [警告] TIF Tag 和 Filename 都無法解析 {filename} 的日期。使用現在時間。 錯誤: {e}")
            item_datetime = datetime.now() # 最終備案

    return item_id, item_datetime, bbox_wgs84, geom_wgs84

# ==== 3. 建立 Catalog 和 Collection ====

print("開始建立 STAC 目錄...")
os.makedirs(ROOT_DIR, exist_ok=True)

# 1) 建立 Catalog
catalog = pystac.Catalog(id=CATALOG_ID, description="我的個人 Capella STAC 目錄")

# 2) 建立 Collection (Extent 稍後自動更新)
collection = pystac.Collection(
    id=COLLECTION_ID,
    description=COLLECTION_DESCRIPTION,
    extent=pystac.Extent(
        spatial=pystac.SpatialExtent(bboxes=[[0,0,0,0]]), # 暫時的
        temporal=pystac.TemporalExtent(intervals=[[datetime.now(), datetime.now()]]) # 暫時的
    ),
    license=LICENSE
)

catalog.add_child(collection)

# ==== 4. 遍歷 TIF，建立 Items 並加入 Collection (v3 簡化) ====

# 搜尋所有 TIF 檔案
tif_files = glob.glob(os.path.join(IMAGE_DIR, "*.tif"))
if not tif_files:
    raise SystemExit(f"在 {IMAGE_DIR} 中找不到任何 .tif 檔案。請檢查路徑。")

print(f"找到了 {len(tif_files)} 個 .tif 檔案，開始處理...")

for tif_path in tif_files:
    try:
        filename = os.path.basename(tif_path) # 僅用於 print
        print(f"  處理中: {filename}")
        
        # --- (v3 簡化) ---
        # 一次性取得所有資訊
        item_id, item_datetime, bbox_wgs84, geom_wgs84 = get_stac_info_from_tif(tif_path)
        
        # 檢查是否為 SLC (被跳過)
        if item_id is None:
            continue # 警告訊息已在函數內印出
        # --- (v3 簡化結束) ---

        # 3. 建立 STAC Item
        item = pystac.Item(
            id=item_id,
            geometry=geom_wgs84,
            bbox=bbox_wgs84,
            datetime=item_datetime,
            properties={} 
        )
        
        # 4. 建立 Asset (指向你的 TIF 檔案)
        tif_abs_path = os.path.abspath(tif_path)
        
        # 決定 Asset 的 roles (角色)
        asset_roles = ["data"]
        if "preview" in filename:
            asset_roles = ["thumbnail"]
        elif "GEC" in filename or "GEO" in filename:
            asset_roles = ["data", "visual"]
        
        item.add_asset(
            key="data",  # 主要資產的鍵
            asset=pystac.Asset(
                href=tif_abs_path, 
                media_type=pystac.MediaType.GEOTIFF,
                title=f"{item_id} (GeoTIFF)",
                roles=asset_roles 
            )
        )
        
        # 5. 將 Item 加入 Collection
        collection.add_item(item)

    except Exception as e:
        print(f"[錯誤] 處理 {tif_path} 失敗: {e}")

# ==== 5. 最終化與存檔 ====

# 1) 自動從所有 Items 更新 Collection 的時空範圍 (Extent)
print("更新 Collection 的 Extent...")
collection.update_extent_from_items()

# 2) 正規化 hrefs (讓 JSON 之間的連結正確)
print("正規化 HREFs...")
catalog.normalize_hrefs(ROOT_DIR)

# 3) 存檔
print(f"儲存 STAC 目錄到 {ROOT_DIR}...")
catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)

print(f"✅ 完成！你的 STAC 目錄在：{os.path.abspath(ROOT_DIR)}")

# ==== 6. 驗證 ====
try:
    cat = pystac.read_file(os.path.join(ROOT_DIR, "catalog.json"))
    cat.describe()
    
    # 顯示第一個 Item 的日期和資產路徑，供檢查
    first_item = next(cat.get_all_items(), None)
    if first_item:
        print("\n--- 驗證第一筆 Item ---")
        print(f"ID: {first_item.id}")
        print(f"Datetime: {first_item.datetime}")
        asset = first_item.assets.get("data")
        if asset:
            print(f"Asset Href (相對路徑): {asset.href}")
        print("---------------------")

except Exception as e:
    print(f"驗證失敗: {e}")
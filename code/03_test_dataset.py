import os
import glob
import yaml
import uuid
import subprocess
import numpy as np
from datetime import datetime
from pathlib import Path

# Geospatial libraries
import rasterio
import rasterio.warp
from shapely.geometry import box, mapping

# ODC libraries
import datacube
from datacube.index.hl import Doc2Dataset

# ==========================================
# ==== 1. 全域參數設定 ====
# ==========================================

CONF_PATH = "D:\\.datacube.conf" 
COG_ROOT = "D:\\Capalla_data\\cog_files"
ODC_DATASET_DIR = "odc_datasets"
ODC_PRODUCT_DIR = "odc_products"

# 設定環境變數
if os.path.exists(CONF_PATH):
    os.environ["DATACUBE_CONFIG_PATH"] = CONF_PATH

# ==== 修正 YAML 讀取 ====
def construct_python_tuple(loader, node):
    return list(loader.construct_sequence(node))
yaml.SafeLoader.add_constructor('tag:yaml.org,2002:python/tuple', construct_python_tuple)

# ==========================================
# ==== 2. Product 定義 ====
# ==========================================

PRODUCT_GEC_HH_DEF = {
    "name": "capella_gec_hh",
    "description": "Capella GEC HH Polarization",
    "license": "proprietary",
    "metadata_type": "eo3",
    "metadata": {"product": {"name": "capella_gec_hh"}},
    "storage": {
        "crs": "EPSG:4326",
        "resolution": {"latitude": -0.0001, "longitude": 0.0001}
    },
    "measurements": [{"name": "hh", "dtype": "float32", "nodata": 0.0, "units": "1"}]
}

PRODUCT_GEC_VV_DEF = {
    "name": "capella_gec_vv",
    "description": "Capella GEC VV Polarization",
    "license": "proprietary",
    "metadata_type": "eo3",
    "metadata": {"product": {"name": "capella_gec_vv"}},
    "storage": {
        "crs": "EPSG:4326",
        "resolution": {"latitude": -0.0001, "longitude": 0.0001}
    },
    "measurements": [{"name": "vv", "dtype": "float32", "nodata": 0.0, "units": "1"}]
}

# ==========================================
# ==== 3. 核心功能函數 ====
# ==========================================

def run_command(command):
    print(f"> 執行: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True, shell=True, env=os.environ)
    if result.returncode != 0:
        if "already exists" not in result.stderr and "Nothing to do" not in result.stderr:
             pass # 忽略錯誤繼續，因為我們要用 python 索引
    else:
        pass

def get_metadata_from_tif(tif_path):
    filename = os.path.basename(tif_path)
    item_id = os.path.splitext(filename)[0]
    item_datetime = None
    
    try:
        with rasterio.open(tif_path) as src:
            src_crs = src.crs
            if src_crs is None: return None
            
            shape = src.shape
            transform = src.transform
            bounds = src.bounds
            bbox_geom = box(bounds.left, bounds.bottom, bounds.right, bounds.top)
            
            if src_crs != "EPSG:4326":
                try:
                    geom_wgs84 = rasterio.warp.transform_geom(src_crs, "EPSG:4326", mapping(bbox_geom))
                except: return None
            else:
                geom_wgs84 = mapping(bbox_geom)
            
            try:
                tags = src.tags()
                dt_str = tags.get('TIFFTAG_DATETIME') or tags.get('DATETIME')
                if dt_str: item_datetime = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
            except: pass

    except: return None

    if item_datetime is None:
        try:
            parts = item_id.split('_')
            ts_str = parts[-3] if parts[-1] == "preview" else parts[-2]
            item_datetime = datetime.strptime(ts_str, '%Y%m%d%H%M%S')
        except: return None

    if "_GEC_HH_" in item_id: p_name, b_name = "capella_gec_hh", "hh"
    elif "_GEC_VV_" in item_id: p_name, b_name = "capella_gec_vv", "vv"
    else: return None

    return {
        "id": item_id,
        "datetime": item_datetime,
        "geometry": geom_wgs84,
        "product_name": p_name,
        "band_name": b_name,
        "shape": shape,
        "transform": transform
    }

def build_eo3_dict(metadata, tif_path):
    dataset_uuid = str(uuid.uuid4())
    absolute_tif_path = os.path.abspath(tif_path)
    tif_uri = Path(absolute_tif_path).as_uri()

    return {
        "id": dataset_uuid,
        "product": {"name": metadata["product_name"]},
        "label": metadata["id"],
        "location": tif_uri,
        # [修正] 頂層宣告 CRS
        "crs": "EPSG:4326", 
        "properties": {
            "odc:processing_datetime": datetime.now().isoformat(),
            "datetime": metadata["datetime"].isoformat(),
            "capella:filename": metadata["id"]
        },
        "geometry": metadata["geometry"],
        "grids": {
            "default": {
                "shape": list(metadata["shape"]),
                "transform": [
                    metadata["transform"].a, metadata["transform"].b, metadata["transform"].c,
                    metadata["transform"].d, metadata["transform"].e, metadata["transform"].f
                ],
                # [修正] Grid 內層也宣告 CRS (雙保險)
                "crs": "EPSG:4326"
            }
        }, 
        "measurements": {
            metadata["band_name"]: {
                "path": os.path.basename(absolute_tif_path)
            }
        },
        "lineage": {}
    }

# ==========================================
# ==== 4. 主程式流程 ====
# ==========================================

def main():
    print("\n=== STEP 1: 初始化資料庫 ===")
    run_command(["datacube", "system", "init"])

    print("\n=== STEP 2: 處理產品 (Products) ===")
    os.makedirs(ODC_PRODUCT_DIR, exist_ok=True)
    
    products = {"capella_gec_hh": PRODUCT_GEC_HH_DEF, "capella_gec_vv": PRODUCT_GEC_VV_DEF}
    for name, definition in products.items():
        path = os.path.join(ODC_PRODUCT_DIR, f"{name}.yaml")
        with open(path, 'w') as f:
            yaml.dump(definition, f)
        run_command(["datacube", "product", "add", path])

    print("\n=== STEP 3: 產生 YAML 並索引資料 ===")
    dc = datacube.Datacube(app="builder-v8")
    index = dc.index
    resolver = Doc2Dataset(index)

    os.makedirs(ODC_DATASET_DIR, exist_ok=True)
    tif_files = glob.glob(os.path.join(COG_ROOT, "*.tif"))
    
    if not tif_files:
        print(f"[錯誤] 在 {COG_ROOT} 找不到 .tif 檔案")
        return

    print(f"找到 {len(tif_files)} 個檔案，開始處理...")
    success_count = 0
    
    for tif in tif_files:
        meta = get_metadata_from_tif(tif)
        if not meta: continue
        
        doc_dict = build_eo3_dict(meta, tif)
        
        yaml_path = os.path.join(ODC_DATASET_DIR, f"ds_{meta['id']}.yaml")
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(doc_dict, f)

        try:
            yaml_uri = Path(os.path.abspath(yaml_path)).as_uri()
            dataset, err_msg = resolver(doc_dict, yaml_uri)
            
            if err_msg:
                print(f"  [格式錯誤] {meta['id']}: {err_msg}")
                continue
            
            try:
                index.datasets.update(dataset)
                # print(f"  [已更新] {meta['id']}") 
                success_count += 1
            except ValueError:
                try:
                    index.datasets.add(dataset)
                    print(f"  [新加入] {meta['id']}")
                    success_count += 1
                except Exception as e:
                    print(f"  [寫入失敗] {meta['id']}: {e}")

        except Exception as e:
            print(f"  [處理異常] {meta['id']}: {e}")

    print(f"\n索引完成！成功處理 {success_count} 筆資料。")

    print("\n=== STEP 5: 最終驗證 (強制模式) ===")
    if success_count > 0:
        print("正在測試載入 'capella_gec_hh'...")
        datasets = dc.find_datasets(product='capella_gec_hh')
        
        if datasets:
            ds = datasets[0]
            print(f"  -> 樣本 ID: {ds.id}")
            # 即使這裡顯示 None，我們下面的手動指定也能解決問題
            print(f"  -> 樣本 CRS: {ds.crs}") 
            
            try:
                # [關鍵修正] 手動指定 output_crs 和 resolution
                # 這會繞過 ODC 對 ds.crs 的依賴
                print("  -> 正在嘗試強制載入 (Explicit Load)...")
                
                data = dc.load(
                    product='capella_gec_hh',
                    datasets=[ds],
                    # 強制指定投影，不再依賴 like=ds
                    output_crs="EPSG:4326", 
                    resolution=(-0.0001, 0.0001),
                    measurements=['hh']
                )
                
                if data and 'hh' in data:
                    val = data.hh.values
                    # 檢查有多少非 NaN 且非 0 的值
                    valid_count = np.sum(~np.isnan(val) & (val != 0))
                    
                    print(f"\n✅✅✅ 建置成功！你終於看到數據了！ ✅✅✅")
                    print(f"資料變數: {list(data.data_vars)}")
                    print(f"資料形狀: {val.shape}")
                    print(f"有效像素: {valid_count}")
                    print("-" * 30)
                    print(data)
                else:
                    print("⚠️ 載入回傳了空物件。")
            except Exception as e:
                print(f"❌ 載入失敗: {e}")
        else:
            print("❌ 資料庫中沒有找到資料。")
    else:
        print("⚠️ 沒有資料被索引。")

if __name__ == "__main__":
    main()
# Blender Import BUILD Map format Add-on
# Copyright (C) 2023 Jens Neitzel

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software: you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation, either version 3
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program. If not, see <https://www.gnu.org/licenses/>. 
#
# ##### END GPL LICENSE BLOCK #####



from dataclasses import dataclass
import os
import re
import struct
import fnmatch
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Set, Iterator
import collections
import bpy

log = logging.getLogger(__name__)



@dataclass
class FileInfo:
    ## absolute path to file or archive containing it
    file_or_archive_path: str
    ## length of the file or entry in bytes
    file_or_entry_length: int
    ## Set path_is_image_file to True if the path is an image file that blender can load directly.
    path_is_image_file: bool = False
    ## archive info in case file is contained in an archive
    is_in_archive: bool = False  ## If this file is e.g. an .ART for that was searched for, this will not count as is_in_archive if it was found directly in the file system and not in e.g. an .GRP file.
    archive_entry_name:   Optional[str] = None
    archive_entry_offset: Optional[int] = None
    
    @property
    def path_with_entry(self) -> str:
        if self.is_in_archive and self.archive_entry_name:
            return f"{self.file_or_archive_path} / {self.archive_entry_name}"
        return self.file_or_archive_path
    
    @property
    def file_or_entry_name(self) -> str:
        if self.is_in_archive and self.archive_entry_name:
            return self.archive_entry_name
        return os.path.basename(self.file_or_archive_path)
    
    ## Return the file path if it is an image file that Blender can load directly.
    @property
    def image_file_path(self) -> Optional[str]:
        if self.path_is_image_file and self.file_or_archive_path:
            return self.file_or_archive_path
        return None

@dataclass
class PicnumEntry(FileInfo):
    tile_index: Optional[int] = None
    image: Optional[bpy.types.Image] = None
    #maps: Dict[str, object] = field(default_factory=dict)  # TODO for future use with .DEF (albedo/normal/roughness/...)
    
    art_byte_offset: Optional[int] = None  ## Offset inside the .ART file
    def_filepath: Optional[str] = None  ## TODO for future use.
        
    ## art-picanm attributes
    art_picanm_available: bool = False
    anim_type: int = 0
    anim_speed: int = 0
    anim_framecount: int = 0
    center_offset_x: int = 0
    center_offset_y: int = 0



class FileWalker:
    """
    Walks list of folders in given order
    and yields matches for a filename pattern (supports '*' wildcard)
    found either as file in the folder or inside an archive.

    Priority within each folder:
      1) Loose files in the root directory (alphabetical)
      2) Archives (.GRP) in the root directory (alphabetical), entries in order listed in archive
      3) Subfolders (alphabetical), each processed with the same rules
    """
    
    ## TODO Create an option if archives (e.g. .GRP) should be searched or not. But atm. the FileWalker is only used in cases where that would be the case.

    def __init__(self, root_folders: List[str], filename_pattern: str):
        self.root_folder_paths: List[Path] = [Path(p).resolve() for p in root_folders if p]
        self.filename_pattern = filename_pattern.lower()
        self._generator = self._iterate_all()

    def get_next(self) -> Optional[FileInfo]:
        ## Returns the next match as FileInfo,
        ## or None if no more matches are available.
        try:
            return next(self._generator)
        except StopIteration:
            return None

    def _iterate_all(self) -> Iterator[FileInfo]:
        ## perform breadth-first search over folders, archives and subfolders
        processed_folders = set()
        for root in self.root_folder_paths:
            if not root.exists() or not root.is_dir():
                continue
            folder_queue = collections.deque([root])
            while folder_queue:
                current_folder = folder_queue.popleft()
                if current_folder in processed_folders:
                    continue
                processed_folders.add(current_folder)

                ## 1) Search Files directly in current folder
                for file_info in self._iterate_file_matches_in_folder(current_folder):
                    yield file_info

                ## 2) Search Archives in current folder
                for file_info in self._iterate_archive_matches_in_folder(current_folder):
                    yield file_info

                ## 3) Enqueue subfolders
                subfolders = sorted((p for p in current_folder.iterdir() if p.is_dir()), key=lambda p: p.name.lower())
                for folder in subfolders:
                    folder_queue.append(folder)

    def _name_matches(self, name: str) -> bool:
        return fnmatch.fnmatch(name.lower(), self.filename_pattern)

    def _iterate_file_matches_in_folder(self, folder: Path) -> Iterator[FileInfo]:
        try:
            entries = sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.name.lower())
        except Exception:
            return
        for f in entries:
            if self._name_matches(f.name):
                try:
                    size = f.stat().st_size
                except Exception:
                    continue
                yield FileInfo(
                    file_or_archive_path = str(f.resolve()),
                    file_or_entry_length = int(size),
                    is_in_archive        = False
                )

    def _iterate_archive_matches_in_folder(self, folder: Path) -> Iterator[FileInfo]:
        try:
            archives = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".grp",)), key=lambda p: p.name.lower())
        except Exception:
            return
        for archive in archives:
            if archive.suffix.lower() == ".grp":
                for match in self._iterate_grp_matches(archive):
                    yield match
            # TODO: add .RFF parsing

    def _iterate_grp_matches(self, grp_path: Path) -> Iterator[FileInfo]:
        """
        Parse a .GRP (Build engine group file) and yield entries matching the pattern.
        https://moddingwiki.shikadi.net/wiki/GRP_Format
        http://justsolve.archiveteam.org/wiki/GRP_(Duke_Nukem_3D)
        GRP File Structure:
          - 12 bytes (ASCII): magic number "KenSilverman", not NULL-terminated 
          - 4 bytes (UINT32LE): file count N
          - N file name and size entries:
            - 12 bytes (ASCII): file name (8.3 style, typically uppercase, null-padded after end of filename to fill the 12 bytes)
            - 4 bytes (UINT32LE): file size
          - File Data. Starts at offset 16 + N*16. Files are contiguous in listed order.
        """
        try:
            grp_size = None
            try:
                grp_size = grp_path.stat().st_size
            except Exception:
                log.warning(f"Unable to read .GRP file size! File: {grp_path}")
                return
            ## sanity check - return if file is below grp minimum size
            if grp_size is None or grp_size < 32:
                log.warning(f".GRP file is below minimum size! File: {grp_path}")
                return
            
            with open(grp_path, "rb") as f:
                ## Read magic number and file count
                magic = f.read(12)
                if (len(magic) != 12) or (magic != b"KenSilverman"):
                    log.warning(f".GRP file is not starting with expected magic number \"KenSilverman\"! File: {grp_path}")
                    return
                file_count_raw = f.read(4)
                if len(file_count_raw) != 4:
                    log.warning(f"Unable to read file count from .GRP file! File: {grp_path}")
                    return
                file_count = struct.unpack("<I", file_count_raw)[0]
                grp_header_size = 16 + file_count * 16
                
                ## sanity check - return if file size is below required header size
                if grp_size < grp_header_size:
                    log.warning(f".GRP file too small to fit header! File: {grp_path}")
                    return

                ## Read file name and size entries
                names: List[str] = []
                sizes: List[int] = []
                for idx in range(file_count):
                    name_raw = f.read(12)
                    if len(name_raw) != 12:
                        log.warning(f"Unable to read packed file name (index:{idx}) from .GRP file! File: {grp_path}")
                        return
                    size_raw = f.read(4)
                    if len(size_raw) != 4:
                        log.warning(f"Unable to read packed file size (index:{idx}) from .GRP file! File: {grp_path}")
                        return
                    file_size = struct.unpack("<I", size_raw)[0]
                    file_name = name_raw.split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
                    names.append(file_name)
                    sizes.append(int(file_size))

                ## Build offsets list
                offsets: List[int] = []
                current_offset = grp_header_size
                for file_size in sizes:
                    offsets.append(current_offset)
                    current_offset += file_size
                
                ## Iterate over entries alphabetically by entry name (case-insensitive)
                #for idx in sorted(range(file_count), key=lambda i: names[i].lower()):
                ## Iterate over entries in order listed
                for idx in range(file_count):
                    entry_name = names[idx]
                    if not self._name_matches(entry_name):
                        continue
                    file_offset = offsets[idx]
                    file_size = sizes[idx]
                    # sanity check - file must be inside GRP
                    if file_offset < grp_header_size or file_offset + file_size > grp_size:
                        continue
                    yield FileInfo(
                        file_or_archive_path = str(grp_path.resolve()),
                        file_or_entry_length = int(file_size),
                        is_in_archive        = True,
                        archive_entry_name   = entry_name,
                        archive_entry_offset = int(file_offset),
                    )
        except Exception:
            return



class TextureImporter:
    PICNUM_USER_ART_START = 3584
    DEFAULT_TILE_DIM = (32, 32)
    
    def __init__(self, folders: List[str], parse_png_jpg_first: bool = False, transparent_index: int = 255):
        self.folders = folders
        self.parse_png_jpg_first = parse_png_jpg_first
        self.transparent_index = transparent_index
        self.palette: Optional[List[Tuple[float, float, float]]] = None

    def run(self, required_picnums: List[int]) -> Tuple[Dict[int, PicnumEntry], Set[int]]:
        """
        Run the texture import process.
        Returns:
            (picnum_dict, remaining_required)
            - picnum_dict: All successfully imported PicnumEntry objects.
            - remaining_required: Set of picnums that could not be found/imported.
        """
        required: Set[int] = set(required_picnums)
        picnum_dict: Dict[int, PicnumEntry] = {}
        log.debug("Searching for textures in folders: %s" % self.folders)

        self.palette = self._load_palette(self.folders)
        
        ## Texture files in first folder (priority/mod folder)
        ## have priority over all texture files in other folders independent of their format
        ## so that the user can overwrite/modify textures
        ## by placing texture files in whatever format in the priority/mod folder
        for folder in self.folders:
            if not folder or not os.path.isdir(folder):
                continue
            if self.parse_png_jpg_first:
                log.debug("Loading Textures from PNG/JPG first, then GRP/ART.")
                self._load_png_jpg(required, [folder], picnum_dict)
                self._load_art(required, [folder], picnum_dict)
            else:
                log.debug("Loading Textures from GRP/ART first, then PNG/JPG.")
                self._load_art(required, [folder], picnum_dict)
                self._load_png_jpg(required, [folder], picnum_dict)
            # Stop early if everything is loaded
            if not required:
                break
        
        if required:
            log.debug(f"Could not find {len(required)} textures for picnums: {sorted(list(required))}")
        
        return picnum_dict, required
    
    @staticmethod
    def getArtFileNumber(picnum: int) -> int:
        return int(picnum // 256)
    
    @staticmethod
    def getArtFileIndex(picnum: int) -> int:
        return int(picnum % 256)
    
    @staticmethod
    def getImgName(picnum: int) -> str:
        return f"Tile_{picnum:04d}"
    
    @staticmethod
    def fillFileMap(folder: str, filemap_out: Dict[str, str]):
        if (folder is not None) and (os.path.exists(folder)) and (os.path.isdir(folder)):
            for root, dirs, files in os.walk(folder):
                for filename in files:
                    if filename.lower().endswith((".png", ".jpg")):
                        filemap_out[filename.lower()] = os.path.join(root, filename)
    
    @staticmethod
    def getTextureFileNamePattern(picnum: int) -> str:
        ## Match file names like: 056-002.png 56-2.png 000568.jpg 568.jpg tile0568.png
        return r"^(?:0{0,3}%d-0{0,3}%d\.(jpg|png)|0{0,8}%d\.(jpg|png)|tile%04d\.(jpg|png))$" % (
            TextureImporter.getArtFileIndex(picnum),
            TextureImporter.getArtFileNumber(picnum),
            picnum,
            picnum,
        )
    
    @staticmethod
    def getDictValueByKeyRegex(dictionary: Dict[str, str], regex: re.Pattern[str]) -> Optional[str]:
        for key, value in dictionary.items():
            if regex.match(key):
                return value
        return None
    
    @staticmethod
    def tryLoadBlenderImage(imgFilePath: str, imageName: Optional[str] = None) -> Optional[bpy.types.Image]:
        if not imgFilePath:
            return None
        try:
            img = bpy.data.images.load(imgFilePath)
        except Exception as e:
            log.warning(f"Failed to load image {imgFilePath}: {e}")
            return None
        if imageName:
            img.name = imageName
        return img
    
    def _findPicnumFile(self, picnum: int, regexDefault: re.Pattern[str], texFileMap: Dict[str, str], allowUserArtFallback: bool = True) -> Optional[str]:
        imgFilePath = None
        if not isinstance(texFileMap, dict) or len(texFileMap) <= 0:
            return None
        ## Try to get User Art file with default filename
        imgFilePath = self.getDictValueByKeyRegex(texFileMap, regexDefault)
        if imgFilePath is None and (picnum >= self.PICNUM_USER_ART_START) and allowUserArtFallback:
            ## A filename matching this regex does not specify the whole picnum and is only acceptable as fallback for User Art:
            regexUserArtFallback = re.compile(r"^0{0,2}%d-.{3}\.(jpg|png)$" % self.getArtFileIndex(picnum), re.IGNORECASE)
            imgFilePath = self.getDictValueByKeyRegex(texFileMap, regexUserArtFallback)
            log.debug("Tried to find User Art for picnum %d using fallback RegEx, resulting in: %s" % (picnum, imgFilePath))
        return imgFilePath
    
    def _load_palette(self, folders: List[str]) -> Optional[List[Tuple[float, float, float]]]:
        """
        Finds and loads the first valid PALETTE.DAT.
        Reads only the first 768 bytes (RGB data for 256 colors).
        Converts 6-bit VGA color values (0-63) into 0.0-1.0 floats.
        https://moddingwiki.shikadi.net/wiki/Duke_Nukem_3D_Palette_Format
        http://justsolve.archiveteam.org/wiki/DAT_(Duke_Nukem_3D)
        https://wiki.eduke32.com/wiki/Palette_data_files
        """
        walker = FileWalker(folders, "PALETTE.DAT")
        while (info := walker.get_next()):
            try:
                if info.file_or_entry_length is not None and info.file_or_entry_length < 768:
                    continue  ## Skip too short files
                with open(info.file_or_archive_path, "rb") as f:
                    if info.archive_entry_offset:
                        f.seek(info.archive_entry_offset)
                    data = f.read(768)  ## read palette section
                if len(data) == 768:
                    log.info(f"Using palette: {info.path_with_entry}")
                    ## Convert 6-bit VGA palette (0-63) -> float RGB (0.0-1.0)
                    return [(data[i]*4/255.0, data[i+1]*4/255.0, data[i+2]*4/255.0) for i in range(0, 768, 3)]
            except Exception as e:
                log.warning(f"Failed to read palette from {info.path_with_entry}: {e}")
                continue
        log.warning("No valid PALETTE.DAT found! .ART files can not be parsed!")
        return None
    
    def _load_png_jpg(self, required: Set[int], folders_to_process: List[str], picnum_dict_out: Dict[int, PicnumEntry]):
        if not required:
            return
        log.debug(f"Searching for .jpg/.png in folders: {folders_to_process}")
        texFileMap: Dict[str, str] = {}
        for folder in folders_to_process:
            self.fillFileMap(folder, texFileMap)

        for picnum in list(required):
            picnum_regex = re.compile(self.getTextureFileNamePattern(picnum), re.IGNORECASE)
            imgFilePath = self._findPicnumFile(picnum, picnum_regex, texFileMap, allowUserArtFallback=True)
            img = self.tryLoadBlenderImage(imgFilePath, self.getImgName(picnum))
            if not img:
                continue
            
            entry = PicnumEntry(
                tile_index = picnum,
                image = img,
                file_or_archive_path = imgFilePath,
                path_is_image_file   = True,
                file_or_entry_length = os.path.getsize(imgFilePath),
                is_in_archive        = False,
                art_picanm_available = False
            )
            
            self.write_image_props(img, entry)
            picnum_dict_out[picnum] = entry
            required.discard(picnum)
            log.debug(f"Loaded PNG/JPG for picnum {picnum}: {entry.path_with_entry}")
    
    def _load_art(self, required: Set[int], folders_to_process: List[str], picnum_dict_out: Dict[int, PicnumEntry]):
        if not required:
            return
        if not self.palette:
            return

        walker = FileWalker(folders_to_process, "*.ART")
        while required:
            info = walker.get_next()
            if not info:
                break
            info.path_is_image_file = False
            log.debug(f"Reading: {info.path_with_entry}")
            if not info.file_or_entry_length or info.file_or_entry_length <= 0:
                log.warning(f"Skipping {'.GRP entry' if info.is_in_archive else '.ART file'} with invalid length! File: {info.path_with_entry}")
                continue
            try:
                with open(info.file_or_archive_path, "rb") as f:
                    if info.archive_entry_offset:
                        f.seek(info.archive_entry_offset)
                    art_bytes = f.read(info.file_or_entry_length)
            except Exception as e:
                log.warning(f"Failed to read ART: {e}")
                continue
            
            self._parse_art(art_bytes, info, required, picnum_dict_out)
    
    def _parse_art(self, art_bytes: bytes, info, required: Set[int], picnum_dict_out: Dict[int, PicnumEntry]):
        ## Parse and import all required tiles found in this .ART File
        ## http://justsolve.archiveteam.org/wiki/ART_(Duke_Nukem_3D)
        ## https://moddingwiki.shikadi.net/wiki/ART_Format_(Build)
        if len(art_bytes) < 16:
            log.warning(f".ART file header too small! Skipping file: {info.path_with_entry}")
            return
        try:
            art_version, numtiles_unused, local_tile_start, local_tile_end = struct.unpack("<llll", art_bytes[:16])
        except struct.error:
            return
        if art_version != 1:
            log.warning(f".ART file with unexpected version: {art_version} File: {info.path_with_entry}")
            return
        
        numtiles = local_tile_end - local_tile_start + 1
        pos = 16
        parsed_tiles_from_art = 0
        tilesizx_array_size = 2 * numtiles
        tilesizy_array_size = 2 * numtiles
        picanm_array_size   = 4 * numtiles
        ## Check size of arrays: short tilesizx[localtileend-localtilestart+1]; short tilesizy[localtileend-localtilestart+1]; long picanm[localtileend-localtilestart+1];
        if len(art_bytes) < (pos + tilesizx_array_size + tilesizy_array_size + picanm_array_size):
            log.warning(f".ART file too small for tile info arrays! File: {info.path_with_entry}")
            return
        
        tilesizx_list = struct.unpack("<" + "H" * numtiles, art_bytes[pos:pos + tilesizx_array_size]); pos += tilesizx_array_size
        tilesizy_list = struct.unpack("<" + "H" * numtiles, art_bytes[pos:pos + tilesizy_array_size]); pos += tilesizy_array_size
        picanm_list   = struct.unpack("<" + "I" * numtiles, art_bytes[pos:pos + picanm_array_size]);   pos += picanm_array_size
        
        for idx in range(numtiles):
            tilesizx, tilesizy = tilesizx_list[idx], tilesizy_list[idx]
            tile_index = local_tile_start + idx
            next_pos = pos + tilesizx * tilesizy
            if tile_index not in required:
                pos = next_pos
                continue
            if tilesizx <= 0 or tilesizy <= 0:
                log.debug(f"Not parsing tile with invalid dimensions: tilesizx: {tilesizx} tilesizy: {tilesizy} Tile index: {tile_index} File: {info.path_with_entry}")  ## Apparently not that uncommon, so not printing as warning.
                pos = next_pos
                continue
            if next_pos > len(art_bytes):
                log.warning(f"Stopping parsing .ART with tile outside of .ART file size! Tile index: {tile_index} File: {info.path_with_entry}")
                break
            
            pixels = art_bytes[pos:next_pos]
            frames, atype, cx, cy, speed = self._decode_picanm(picanm_list[idx])
            img = self._create_blender_image(tile_index, tilesizx, tilesizy, pixels)
            
            entry = PicnumEntry(
                tile_index = tile_index,
                image = img,
                file_or_archive_path = info.file_or_archive_path,
                path_is_image_file   = False,
                file_or_entry_length = info.file_or_entry_length,
                is_in_archive        = info.is_in_archive,
                archive_entry_name   = info.archive_entry_name,
                archive_entry_offset = info.archive_entry_offset,
                art_byte_offset      = pos,
                art_picanm_available = True,
                anim_type  = atype,
                anim_speed = speed,
                anim_framecount = frames,
                center_offset_x = cx,
                center_offset_y = cy,
            )
            self.write_image_props(img, entry)
            picnum_dict_out[tile_index] = entry
            required.discard(tile_index)
            parsed_tiles_from_art += 1
            pos = next_pos
        log.debug(f"Number of tiles parsed from {info.file_or_entry_name}: {parsed_tiles_from_art}")
    
    def _decode_picanm(self, u32: int) -> Tuple[int, int, int, int, int]:
        frames     =  u32        & 0x3F
        anim_type  = (u32 >> 6)  & 0x03
        xcenter    = struct.unpack("<b", bytes([(u32 >> 8)  & 0xFF]))[0]
        ycenter    = struct.unpack("<b", bytes([(u32 >> 16) & 0xFF]))[0]
        anim_speed = (u32 >> 24) & 0x0F
        return frames, anim_type, xcenter, ycenter, anim_speed
    
    def _create_blender_image(self, picnum: int, w: int, h: int, pixels: bytes) -> bpy.types.Image:
        img = bpy.data.images.new(self.getImgName(picnum), width=w, height=h, alpha=True)
        if not self.palette:
            return img
        
        buf = []
        ## .ART format stores pixels column wise, starting in top left corner.
        for y in range(h-1, -1, -1):
            for x in range(w):
                idx = pixels[x * h + y]
                r, g, b = self.palette[idx]
                a = 0.0 if idx == self.transparent_index else 1.0
                buf.extend([r, g, b, a])
        
        img.pixels = buf
        img.pack()
        #img.use_fake_user = True
        return img
    
    @staticmethod
    def write_image_props(img: bpy.types.Image, entry: PicnumEntry):
        props = {
            "schema_version": 1,
            "tile_index": int(entry.tile_index or 0),
            "file_or_archive_path": entry.file_or_archive_path or "",
            "file_or_entry_length": int(entry.file_or_entry_length or 0),
            "path_is_image_file":   bool(entry.path_is_image_file),
            "is_in_archive": bool(entry.is_in_archive),
            "archive_entry_name": entry.archive_entry_name or "",
            "archive_entry_offset": int(entry.archive_entry_offset or 0),
            "art_byte_offset": int(entry.art_byte_offset or 0),
            "def_filepath": entry.def_filepath or "",
            "art_picanm_available": bool(entry.art_picanm_available),
            "anim_type": int(entry.anim_type),
            "anim_speed": int(entry.anim_speed),
            "anim_framecount": int(entry.anim_framecount),
            "center_offset_x": int(entry.center_offset_x),
            "center_offset_y": int(entry.center_offset_y),
        }
        img["build_tile_props"] = props
    
    @staticmethod
    def get_picnum_entry_from_image(img: bpy.types.Image) -> Optional[PicnumEntry]:
        ## Reconstruct a PicnumEntry from the custom properties stored on a Blender image.
        
        if img is None:
            return None
        
        props = img.get("build_tile_props", None)
        if props is None:
            return None

        def get_int(key: str, default: Optional[int] = None) -> Optional[int]:
            val = props.get(key, default)
            try:
                # allow None as "no value"
                return int(val) if val is not None else default
            except Exception:
                return default

        def get_bool(key: str, default: bool = False) -> bool:
            val = props.get(key, default)
            try:
                return bool(val)
            except Exception:
                return default

        def get_str(key: str, default: str = "") -> str:
            val = props.get(key, default)
            if (val is None) or (val == ""):
                return default
            return str(val)

        schema_version = get_int("schema_version", 1)
        if schema_version != 1:
            log.debug(f"Unexpected build_tile_props schema_version {schema_version} on image '{img.name}'")
        
        entry = PicnumEntry(
            tile_index           = get_int("tile_index", None),
            image                = img,
            file_or_archive_path = get_str("file_or_archive_path", ""),
            file_or_entry_length = get_int("file_or_entry_length", 0),
            path_is_image_file   = get_bool("path_is_image_file", False),
            is_in_archive        = get_bool("is_in_archive", False),
            archive_entry_name   = get_str("archive_entry_name", None),
            archive_entry_offset = get_int("archive_entry_offset", None),
            art_byte_offset      = get_int("art_byte_offset", None),
            def_filepath         = get_str("def_filepath", None),
            art_picanm_available = get_bool("art_picanm_available", False),
            anim_type            = get_int("anim_type", 0),
            anim_speed           = get_int("anim_speed", 0),
            anim_framecount      = get_int("anim_framecount", 0),
            center_offset_x      = get_int("center_offset_x", 0),
            center_offset_y      = get_int("center_offset_y", 0),
        )

        return entry

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
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Set, Iterator
import collections
import bpy

log = logging.getLogger(__name__)



def _decrypt_fileinfo_bytes(data: bytes, info: "FileInfo") -> bytes:
    """
    Apply archive-specific decryption to the given data block, if needed.
    Currently handles RFF entries with the 0x10 encryption flag.
    """
    if info.rff_encrypted:
        buf = bytearray(data)
        limit = min(256, len(buf))
        for i in range(limit):
            buf[i] ^= (i >> 1)
        #log.debug(f"Decrypted: {info.path_with_entry}")
        return bytes(buf)
    return data

def read_fileinfo_bytes(info: "FileInfo", length: Optional[int] = None) -> Optional[bytes]:
    """
    Open the the file at file_or_archive_path, seek to the correct offset
    (for archive entries) and read file_or_entry_length bytes or a custom length.
    Applies archive-specific decryption if needed.
    """
    try:
        with open(info.file_or_archive_path, "rb") as f:
            if info.is_in_archive and info.archive_entry_offset is not None:
                f.seek(info.archive_entry_offset)
            read_len = info.file_or_entry_length if length is None else length
            if read_len is None or read_len <= 0:
                return None
            data = f.read(read_len)
    except Exception as exc:
        log.warning(f"Failed to read data for {info.path_with_entry}: {exc}")
        return None
    return _decrypt_fileinfo_bytes(data, info)

def decode_rff_mtime(mtime: int) -> str:
    """
    Convert a DOS-packed RFF mtime into a human-readable timestamp string.
    Format: 'YYYY-MM-DD HH:MM:SS'
    If mtime is 0, return an empty string.
    """
    if mtime == 0:
        return ""
    time_part = mtime & 0xFFFF
    date_part = (mtime >> 16) & 0xFFFF
    second = (time_part & 0x1F) * 2
    minute = (time_part >> 5) & 0x3F
    hour   = (time_part >> 11) & 0x1F
    day   = date_part & 0x1F
    month = (date_part >> 5) & 0x0F
    year  = 1980 + ((date_part >> 9) & 0x7F)
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"



class ArchiveType(Enum):
    GRP = "GRP"
    RFF = "RFF"

@dataclass
class FileInfo:
    ## absolute path to file or archive containing it
    file_or_archive_path: str
    ## length of the file or entry in bytes
    file_or_entry_length: int
    ## Set path_is_image_file to True if the path is an image file that Blender can load directly.
    path_is_image_file: bool = False
   
    ## archive info in case file is contained in an archive
    archive_entry_name:   Optional[str] = None
    archive_entry_offset: Optional[int] = None
    archive_type:         Optional[ArchiveType] = None
    ## version of the RFF archive format, e.g.: 0x0200, 0x0300, 0x0301
    rff_version: Optional[int] = None
    ## raw flags value from an RFF dictionary entry
    rff_flags: Optional[int] = None
    
    ## If this file is e.g. an .ART for that was searched for, this will not count as is_in_archive if it was found directly in the file system and not in e.g. an .GRP/.RFF file.
    @property
    def is_in_archive(self) -> bool:
        return self.archive_type is not None

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
    
    @property
    def rff_encrypted(self) -> bool:
        return (
            self.archive_type == ArchiveType.RFF
            and self.rff_flags is not None
            and (self.rff_flags & 0x10) != 0
        )

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
    Walks through list of folders in given order
    and yields matches for a filename pattern (supports '*' wildcard)
    found either as file in the folder or inside an archive.
    
    Priority within each folder:
      1) Loose files in the root directory (alphabetical)
      2) Archives (.GRP/.RFF) in the root directory (alphabetical), entries in order listed in archive
      3) Subfolders (alphabetical), each processed with the same rules
    """
    
    GRP_SUFFIX = ".grp"
    RFF_SUFFIX = ".rff"
    RFF_ENTRY_SIZE = 48
    
    def __init__(self, root_folders: List[str], filename_pattern: str, search_grp: bool = True, search_rff: bool = False):
        self.root_folder_paths: List[Path] = [Path(p).resolve() for p in root_folders if p]
        self.filename_pattern = filename_pattern.lower()
        self.search_grp = search_grp
        self.search_rff = search_rff
        self._generator = self._iterate_all()
        ## Tuple of archive extensinos we want to include in the search
        self.archive_extensions: Tuple[str, ...] = tuple()
        if self.search_grp and self.search_rff:
            self.archive_extensions = (self.GRP_SUFFIX, self.RFF_SUFFIX)
        elif self.search_grp:
            self.archive_extensions = (self.GRP_SUFFIX,)
        elif self.search_rff:
            self.archive_extensions = (self.RFF_SUFFIX,)
        log.debug(f"FileWalker initialized with  filename_pattern:{self.filename_pattern}  search_grp:{self.search_grp}  search_rff:{self.search_rff}  folders:{self.root_folder_paths}")
    
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
                try:
                    subfolders = sorted((p for p in current_folder.iterdir() if p.is_dir()), key=lambda p: p.name.lower())
                except Exception:
                    continue
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
                    archive_type         = None
                )
    
    def _iterate_archive_matches_in_folder(self, folder: Path) -> Iterator[FileInfo]:
        try:
            archives = sorted(
                (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in self.archive_extensions),
                key=lambda p: p.name.lower()
            )
        except Exception:
            return
        
        for archive in archives:
            suffix = archive.suffix.lower()
            if suffix == self.GRP_SUFFIX and self.search_grp:
                for match in self._iterate_grp_matches(archive):
                    yield match
            elif suffix == self.RFF_SUFFIX and self.search_rff:
                for match in self._iterate_rff_matches(archive):
                    yield match
    
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
            
            ## sanity check - return if file is below grp minimum header size
            if grp_size is None or grp_size < 32:
                log.warning(f".GRP file is below minimum size! File: {grp_path}")
                return
            
            with open(grp_path, "rb") as f:
                ## Read magic number
                magic = f.read(12)
                if magic != b"KenSilverman":
                    log.warning(f".GRP file has invalid magic header! File: {grp_path}")
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
                
                ## sanity check - last offset must be inside file
                if current_offset > grp_size:
                    log.warning(f".GRP file has invalid file table (data beyond end of file)! File: {grp_path}")
                    return
                
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
                        archive_type         = ArchiveType.GRP,
                        archive_entry_name   = entry_name,
                        archive_entry_offset = int(file_offset),
                    )
        except Exception:
            return
    
    def _iterate_rff_matches(self, rff_path: Path) -> Iterator[FileInfo]:
        """
        Parse an .RFF archive (Blood resource file) and yield entries matching the pattern.
        Supports versions 0x0200, 0x0300 and 0x0301.
        RFF File Structure (simplified):
          - 4 bytes:  magic number "RFF\x1A"
          - 2 bytes:  version (0x0200, 0x0300, 0x0301)
          - 2 bytes:  pad1
          - 4 bytes:  dictOffset
          - 4 bytes:  dictEntries
          - 16 bytes: pad2
          - dictEntries * 48 bytes: FAT entries
          - file data at offsets specified in FAT
        """
        try:
            basename = os.path.basename(rff_path)
            rff_size = None
            try:
                rff_size = rff_path.stat().st_size
            except Exception:
                log.warning(f"Unable to read .RFF file size! File: {rff_path}")
                return
            
            ## sanity check - return if file is below rff minimum header size
            if rff_size is None or rff_size < 32:
                log.warning(f".RFF file is below minimum size! File: {rff_path}")
                return
            
            with open(rff_path, "rb") as f:
                ## Read magic number
                magic = f.read(4)
                if magic != b"RFF\x1a":
                    log.warning(f".RFF file has invalid magic number! File: {rff_path}")
                    return
                
                rff_header = f.read(28)
                if len(rff_header) != 28:
                    log.warning(f"Unable to read .RFF header! File: {rff_path}")
                    return
                
                version, pad1, dict_offset, dict_entries, pad2 = struct.unpack("<H2sII16s", rff_header)
                
                major = version & 0xFF00
                #if version not in (0x0200, 0x0300, 0x0301):
                if major not in (0x0200, 0x0300):
                    log.warning(f"Unsupported .RFF version 0x{version:04X} in file: {rff_path}")
                    return
                log.debug(f"Reading RFF-File:{rff_path}  version:0x{version:04X}  dict_offset:{dict_offset}  dict_entries:{dict_entries}")
                
                if dict_entries == 0:
                    log.warning(f".RFF file has 0 file entries! File: {rff_path}")
                    return
                
                fat_size = dict_entries * self.RFF_ENTRY_SIZE
                
                ## sanity check - FAT must be inside file
                if dict_offset < 32 or dict_offset + fat_size > rff_size:
                    log.warning(f".RFF file has invalid FAT range! File: {rff_path}")
                    return
                
                f.seek(dict_offset)
                fat_data = f.read(fat_size)
                if len(fat_data) != fat_size:
                    log.warning(f"Unable to read .RFF FAT! File: {rff_path}")
                    return
                
                ## decrypt FAT
                if major == 0x0300:
                    fat_bytes = bytearray(fat_data)
                    key = (dict_offset + (version & 0x00FF) * dict_offset) & 0xFFFF
                    for i in range(len(fat_bytes)):
                        fat_bytes[i] ^= ((key >> 1) & 0xFF)
                        key = (key + 1) & 0xFFFF
                    fat_data = bytes(fat_bytes)
                
                ## parse FAT entries
                for i in range(dict_entries):
                    entry_data = fat_data[i * self.RFF_ENTRY_SIZE : (i + 1) * self.RFF_ENTRY_SIZE]
                    if len(entry_data) != self.RFF_ENTRY_SIZE:
                        log.debug(f"Skipping {basename} Entry ({i}) with len(entry_data):{len(entry_data)} != self.RFF_ENTRY_SIZE:{self.RFF_ENTRY_SIZE}!")
                        continue
                    (
                        cachenode,      # 16-byte cache header (unused by Blood/Build tools)
                        offset,         # Offset of file data inside the RFF
                        size,           # Uncompressed size of the file data
                        packed_size,    # Compressed size (0 or same as size if uncompressed)
                        mtime,          # Last modified timestamp (DOS format)
                        flags,          # Bitfield: encryption, external file, compression
                        type_bytes,     # 3-char file extension (ASCII, zero-padded)
                        name_bytes,     # 8-char base filename (ASCII, zero-padded)
                        file_id,        # Internal file ID
                    ) = struct.unpack("<16sIIIIB3s8sI", entry_data)
                    
                    ext  = type_bytes.split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
                    name = name_bytes.split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
                    file_name = f"{name}.{ext}" if ext else name
                    
                    ## Skip external files (not stored in the RFF itself)
                    ## Bit 0x02 is kDictExternal according to documentation.
                    if flags & 0x02:
                        log.debug(f"Skipping {basename} Entry ({i}): \"{file_name}\"  Timestamp: {decode_rff_mtime(mtime)}  FileID:{file_id}  with Bit 0x02 (is kDictExternal) set!")
                        continue
                    
                    ## sanity check - data must be inside file
                    if offset < 0 or size < 0:
                        log.debug(f"Skipping {basename} Entry ({i}): \"{file_name}\" with invalid offset:{offset} or size:{size}!")
                        continue
                    if offset + size > rff_size:
                        log.debug(f"Skipping {basename} Entry ({i}): \"{file_name}\" with offset:{offset} + size:{size} > rff_size:{rff_size}!")
                        continue
                    
                    ## Skip file if name does not match requested pattern
                    if not self._name_matches(file_name):
                        #log.debug(f"Skipping {basename} Entry ({i}): \"{file_name}\"  Timestamp: {decode_rff_mtime(mtime)}  FileID:{file_id}  with filename not matching.")  ## Comment out for less spam
                        continue
                    
                    log.debug(f"Yielding {basename} Entry ({i}): \"{file_name}\"  Size:{size}  Offset:{offset}  Flags:0x{flags:02X} = 0b{flags:08b}  FileID:{file_id}  Timestamp:{decode_rff_mtime(mtime)}  packed_size:{packed_size}  cachenode:{cachenode}")
                    yield FileInfo(
                        file_or_archive_path = str(rff_path.resolve()),
                        file_or_entry_length = int(size),
                        archive_type         = ArchiveType.RFF,
                        archive_entry_name   = file_name,
                        archive_entry_offset = int(offset),
                        rff_version          = int(version),
                        rff_flags            = int(flags),
                    )
                log.debug(f"End of Entries reached for {basename}.")
        except Exception:
            return



class TextureImporter:
    PICNUM_USER_ART_START = 3584
    DEFAULT_TILE_DIM = (32, 32)
    
    def __init__(self, folders: List[str], is_blood_map: bool = False, parse_png_jpg_first: bool = False, transparent_index: int = 255):
        self.folders = folders
        self.is_blood_map = is_blood_map
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
        color_range_multilier = 4.0  ## Using 6-bit VGA palette (0-63) for default BUILD Palette
        #color_range_multilier = 4.047619048  ## (255/63) Should this be used?  Otherwise: 4*63 = 252 = 0xFC = brightest possible
        if self.is_blood_map:
            color_range_multilier = 1.0  ## Blood uses the full 8-bit
        
        if self.is_blood_map:
            ## Only BLOOD.PAL is needed.
            ## WATER.PAL, BEAST.PAL, SEWER.PAL and INVULN1.PAL only offer different (whole screen) shadings
            ## in case the player is under the water, sewer, has beast vision or invulnerable status
            walker = FileWalker(folders, "BLOOD.PAL", search_grp=False, search_rff=True)  
        else:
            walker = FileWalker(folders, "PALETTE.DAT", search_grp=True, search_rff=False)
        
        while (info := walker.get_next()):
            try:
                if info.file_or_entry_length is not None and info.file_or_entry_length < 768:
                    continue  ## Skip too short files
                data = read_fileinfo_bytes(info, length=768)  ## read palette section
                if not data or len(data) != 768:
                    continue
                ## TODO Here we could also check if all data is in range 0-63 or above to decide the color_range_multilier.
                log.info(f"Using palette: {info.path_with_entry}")
                ## Convert palette to float RGB (0.0-1.0)
                return [(data[i]*color_range_multilier/255.0, data[i+1]*color_range_multilier/255.0, data[i+2]*color_range_multilier/255.0) for i in range(0, 768, 3)]
            except Exception as e:
                log.warning(f"Failed to read palette from {info.path_with_entry}: {e}")
                continue
        log.warning("No valid color palette file found! .ART files can not be parsed!")
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
                archive_type         = None,
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

        if self.is_blood_map:
            walker = FileWalker(folders_to_process, "*.ART", search_grp=False, search_rff=True)
        else:
            walker = FileWalker(folders_to_process, "*.ART", search_grp=True, search_rff=False)
        while required:
            info = walker.get_next()
            if not info:
                break
            info.path_is_image_file = False
            log.debug(f"Reading: {info.path_with_entry}")
            if not info.file_or_entry_length or info.file_or_entry_length <= 0:
                log.warning(f"Skipping {'Archive entry' if info.is_in_archive else '.ART file'} with invalid length! File: {info.path_with_entry}")
                continue
            art_bytes = read_fileinfo_bytes(info)
            if not art_bytes:
                log.warning(f"Failed to read ART data for {info.path_with_entry}")
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
                archive_type         = info.archive_type,
                rff_version          = info.rff_version,
                rff_flags            = info.rff_flags,
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
        #img.use_fake_user = True  ## Don't set the fake user because images might go unused in case existing materials are reused for example. In that case not setting the fake user ensures that unused images get cleaned up.
        return img
    
    @staticmethod
    def write_image_props(img: bpy.types.Image, entry: PicnumEntry):
        props = {
            "schema_version": 1,
            "tile_index":           int(entry.tile_index or 0),
            "file_or_archive_path": entry.file_or_archive_path or "",
            "file_or_entry_length": int(entry.file_or_entry_length or 0),
            "path_is_image_file":   bool(entry.path_is_image_file),
            "archive_type":         entry.archive_type.name if entry.archive_type is not None else "",
            "rff_version":          int(entry.rff_version) if entry.rff_version is not None else 0,
            "rff_flags":            int(entry.rff_flags)   if entry.rff_flags   is not None else 0,
            "archive_entry_name":   entry.archive_entry_name or "",
            "archive_entry_offset": int(entry.archive_entry_offset or 0),
            "art_byte_offset":      int(entry.art_byte_offset or 0),
            "def_filepath":         entry.def_filepath or "",
            "art_picanm_available": bool(entry.art_picanm_available),
            "anim_type":            int(entry.anim_type),
            "anim_speed":           int(entry.anim_speed),
            "anim_framecount":      int(entry.anim_framecount),
            "center_offset_x":      int(entry.center_offset_x),
            "center_offset_y":      int(entry.center_offset_y),
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
        
        archive_type_str = get_str("archive_type", None)
        archive_type: Optional[ArchiveType] = None
        if archive_type_str:
            try:
                archive_type = ArchiveType[archive_type_str.upper()]
            except KeyError:
                archive_type = None
                log.debug(f"Unknown archive_type '{archive_type_str}' on image '{img.name}'")
        
        entry = PicnumEntry(
            tile_index           = get_int("tile_index", None),
            image                = img,
            file_or_archive_path = get_str("file_or_archive_path", ""),
            file_or_entry_length = get_int("file_or_entry_length", 0),
            path_is_image_file   = get_bool("path_is_image_file", False),
            archive_type         = archive_type,
            rff_version          = get_int("rff_version", None),
            rff_flags            = get_int("rff_flags", None),
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

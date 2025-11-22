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



from abc import ABC, abstractmethod
from collections import namedtuple
from enum import Enum
import logging
import math
import os
import struct
from typing import BinaryIO, List

from mathutils import Vector

from . import game_tile_lookup

log = logging.getLogger(__name__)



class BuildSector:
    def __init__(self):
        self.data        = None
        self.bmap        = None
        self.sectorIndex = None
        self.walls: List[BuildWall] = []
        self.sprites: List[BuildSprite] = []
        self.wallLoops   = []  ## List of list of walls that form loops
        self.zScal       = {}  ## Dict of Z-coordinate (height) of floor or ceiling at first point of sector
        self.slopeAbs    = {}
        self.slopeVector = {}  ## slope values (float 1 = 45 degrees)
        self.corrupted   = False
        self.level: List[BuildSector.SectLevel] = []
    
    def getPolyLines(self):
        polylines = []
        for wallLoop in self.wallLoops:
            polyline = []
            for wall in wallLoop:
                polyline.append(Vector((wall.xScal, wall.yScal)))
            polylines.append(polyline)
        return polylines
    
    def getLevel(self, ommitTror=True):
        return [lvl for lvl in self.level if not ommitTror or not lvl.isTrorOmit()]
    
    def getFloor(self):
        return self.level[0]
    
    def getCeiling(self):
        return self.level[1]
    
    def getName(self, sky=False, prefix=""):
        if sky:
            return f"{prefix}Sector_{self.sectorIndex:03d}_Sky"
        else:
            return f"{prefix}Sector_{self.sectorIndex:03d}"
    
    def getSpritesString(self):
        return " ".join([str(sprite.spriteIndex) for sprite in self.sprites]).rstrip()


    class SectLevel:
        def __init__(self, parentSector, leveltype):
            self.sector = parentSector
            self.bmap   = parentSector.bmap
            self.type   = leveltype
            if self.type is self.bmap.Level.FLOOR:
                self.zScal = float(self.sector.data.floorz) / 8192
                self.cstat = self.sector.data.floorstat
            else:
                self.zScal = float(self.sector.data.ceilingz) / 8192
                self.cstat = self.sector.data.ceilingstat

        def isFloor(self):
            return self.type is self.bmap.Level.FLOOR

        def isCeiling(self):
            return self.type is self.bmap.Level.CEILING

        def getPicNum(self):
            return self.sector.data.floorpicnum if self.isFloor() else self.sector.data.ceilingpicnum
        
        def getZ(self):
            return self.sector.data.floorz if self.isFloor() else self.sector.data.ceilingz

        def getHeiNum(self):
            return self.sector.data.floorheinum if self.isFloor() else self.sector.data.ceilingheinum

        def getShade(self):
            return self.sector.data.floorshade if self.isFloor() else self.sector.data.ceilingshade
        
        def getShadeColor(self):
            return self.bmap.calculateShadeColor(self.getShade())

        def getPal(self):
            return self.sector.data.floorpal if self.isFloor() else self.sector.data.ceilingpal

        def getXPanning(self):
            return self.sector.data.floorxpanning if self.isFloor() else self.sector.data.ceilingxpanning

        def getYPanning(self):
            return self.sector.data.floorypanning if self.isFloor() else self.sector.data.ceilingypanning
        
        def getTexPanning(self):
            return float(self.getXPanning()) / 256, float(self.getYPanning()) / 256 * -1
        
        def getTexSwapXY(self): ## mapster32: F flip texture
            return bool(self.cstat & 0x4)
        
        def getTexExpansion(self): ## mapster32: E toggle sector texture expansion
            return float(((self.cstat>>3)&1)+1)
        
        def getTexFlipX(self): ## mapster32: F flip texture
            return bool(self.cstat & 0x10)
        
        def getTexFlipY(self): ## mapster32: F flip texture
            return bool(self.cstat & 0x20)
        
        def isTexAlignToFirstWall(self): ## mapster32: R toggle sector texture relativity alignment
            return bool(self.cstat & 0x40)
        
        def getTexFlipXFactor(self):
            return 1 if self.getTexSwapXY() == self.getTexFlipX() else -1
        
        def getTexFlipYFactor(self):
            return 1 if self.getTexSwapXY() == self.getTexFlipY() else -1
        
        def getHeightAtPos(self, xPos, yPos, respectEffectors=False):  ## TODO respectEffectors is experimental for now
            slopeX = self.sector.slopeVector[self.type.name].x
            slopeY = self.sector.slopeVector[self.type.name].y
            zScal = self.zScal
            zC9Sprite = None
            if respectEffectors:
                for sprite in self.sector.sprites:
                    if sprite.data.lotag == 13:  ## C-9 Explosive Sprite moves floor to height of sprite until it explodes
                        zC9Sprite = sprite.zScal
                        break
            if (zC9Sprite is not None) and (self.type == self.bmap.Level.FLOOR):
                zScal = zC9Sprite
            return (self.sector.walls[0].xScal - xPos)*slopeX + (self.sector.walls[0].yScal - yPos)*slopeY + zScal
        
        def isParallaxing(self): ## mapster32: P toggle parallax
            return bool(self.cstat & 0x1)
        
        def isTrorOmit(self):  ## Experimental
            return (self.bmap.tror_supported == True) and bool(self.cstat & 0x400) and ((self.cstat & 0x80) == 0)
        
        def getName(self, sky=False, prefix=""):
            lvlName = "Floor" if self.type == self.bmap.Level.FLOOR else "Ceiling"
            if sky:
                return f"{prefix}Sector_{self.sector.sectorIndex:03d}_{lvlName}_Sky"
            else:
                return f"{prefix}Sector_{self.sector.sectorIndex:03d}_{lvlName}"

class BuildWall:
    def __init__(self):
        self.data = None
        self.bmap = None
        self.indexInMap = None
        self.indexInSector = None
        self.sector = None
        self.xScal = None
        self.yScal = None
        self.neighborSectorIndex       = -1  ## This has in some cases shown more trustworthy results than relying on the walls nextwall and nextsector fields.
        self.neighborWallIndexInSector = -1  ## This has in some cases shown more trustworthy results than relying on the walls nextwall and nextsector fields.
        self.wallParts: List[BuildWall.WallPart] = []
    
    def finalize(self):
        self.startVect = Vector((self.xScal, self.yScal*-1))
        self.endVect   = Vector((self.getPoint2Wall().xScal, self.getPoint2Wall().yScal*-1))
        self.wallVect  = self.endVect - self.startVect
        self.angle     = Vector((1,0)).angle_signed(self.wallVect)
        self.length    = self.wallVect.length
    
    def getPoint2Wall(self):
        if (self.data.point2 < self.sector.data.wallptr) \
                or (self.data.point2 >= self.bmap.data.numwalls) \
                or (self.data.point2 >= (self.sector.data.wallptr + self.sector.data.wallnum)):
            return None
        else:
            return self.bmap.getWall(self.data.point2)
    
    def getNeighborSector(self):
        if (self.neighborSectorIndex < 0) or (self.neighborSectorIndex >= self.bmap.data.numsectors):
            return None
        if self.bmap.sectors[self.neighborSectorIndex].corrupted:
            return None
        return self.bmap.sectors[self.neighborSectorIndex]
    
    def getNeighborWall(self):
        neighborSect = self.getNeighborSector()
        if (neighborSect is None) \
                or (self.neighborWallIndexInSector < 0) \
                or (self.neighborWallIndexInSector >= neighborSect.data.wallnum):
            return None
        else:
            return neighborSect.walls[self.neighborWallIndexInSector]
    
    def getTexBottomSwap(self):
        return bool(self.data.cstat & 0x2)
    
    def getTexAlignFlag(self):
        return bool(self.data.cstat & 0x4)
    
    def getTexRotate(self): ## mapster32: R
        return bool(self.data.cstat & 0x1000)
    
    def getTexFlipXFactor(self):
        return float(1) - float((self.data.cstat >> 3) & 1) * 2
    
    def getTexFlipYFactor(self):
        return float(1) - float((self.data.cstat >> 8) & 1) * 2
    
    def getName(self, useIndexInMap=False, prefix=""):
        if useIndexInMap:
            return f"{prefix}Sector_{self.sector.sectorIndex:03d}_MapWall_{self.indexInMap:03d}"
        else:
            return f"{prefix}Sector_{self.sector.sectorIndex:03d}_SctWall_{self.indexInSector:03d}"
    
    def getWallParts(self):
        if len(self.wallParts) > 0:
            return self.wallParts
        else:
            neighborSector = self.getNeighborSector()
            ## Create a first Wall Part.
            ## In case there is no neighbor Sector, this will remain the only one and it will be a "white" wall.
            self.wallParts.append(self.WallPart(self, neighborSector, isRedTopWall=False))
            if neighborSector is not None:
                ## In case a neighbor sector exists we must create a second wall part.
                ## A Wall that connects to another Sector is a "red" wall that has a bottom and a top part.
                self.wallParts.append(self.WallPart(self, neighborSector, isRedTopWall=True))
            return self.wallParts

    class WallPart:
        def __init__(self, parentWall, neighborSector, isRedTopWall):
            self.wall         = parentWall
            self.bmap         = self.wall.bmap
            self.vertices     = []
            self.wallType     = None
            self.sectBotLevel = None
            self.sectTopLevel = None
            self.alignTexZ    = 0
            self.neighborSector = neighborSector
            self.zBottom      = None
            
            if not isRedTopWall:
                self.sectBotLevel = self.wall.sector.getFloor()
                if self.neighborSector is None:
                    ## Case 1 (simple white wall)
                    self.wallType      = self.bmap.WallType.WHITE
                    self.sectTopLevel  = self.wall.sector.getCeiling()
                    if self.wall.getTexAlignFlag():
                        self.alignTexZ = self.wall.sector.getFloor().zScal     ## Flags = 4: Aligned to floor of own sector
                    else:
                        self.alignTexZ = self.wall.sector.getCeiling().zScal   ## Flags = 0: Aligned to ceiling of own sector
                else:
                    ## Case 2 (bottom portion of red wall)
                    self.wallType      = self.bmap.WallType.REDBOT
                    self.sectTopLevel  = self.neighborSector.getFloor()
                    if self.wall.getTexAlignFlag():
                        self.alignTexZ = self.wall.sector.getCeiling().zScal   ## Flags = 4: Aligned to ceiling of own sector
                    else:
                        self.alignTexZ = self.neighborSector.getFloor().zScal  ## Flags = 0: Aligned to floor of neighbor sector (upper edge of lower wall portion)
            else:
                ## Case 3 (top portion of red wall)
                self.wallType      = self.bmap.WallType.REDTOP
                self.sectBotLevel  = self.neighborSector.getCeiling()
                self.sectTopLevel  = self.wall.sector.getCeiling()
                if self.wall.getTexAlignFlag():
                    self.alignTexZ = self.wall.sector.getCeiling().zScal       ## Flags = 4: Aligned to ceiling of own sector
                else:
                    self.alignTexZ = self.neighborSector.getCeiling().zScal    ## Flags = 0: Aligned to ceiling of neighbor sector (lower edge of upper wall portion)
            
            self.zBottom = self.sectBotLevel.zScal
            point2Wall = self.wall.getPoint2Wall()
            if point2Wall is not None:
                self.vertices.append(Vector(( self.wall.xScal,  self.wall.yScal,  self.sectBotLevel.getHeightAtPos(self.wall.xScal,  self.wall.yScal)  )))
                self.vertices.append(Vector(( point2Wall.xScal, point2Wall.yScal, self.sectBotLevel.getHeightAtPos(point2Wall.xScal, point2Wall.yScal) )))
                self.vertices.append(Vector(( point2Wall.xScal, point2Wall.yScal, self.sectTopLevel.getHeightAtPos(point2Wall.xScal, point2Wall.yScal) )))
                self.vertices.append(Vector(( self.wall.xScal,  self.wall.yScal,  self.sectTopLevel.getHeightAtPos(self.wall.xScal,  self.wall.yScal)  )))
        
        def getClippedVertices(self):
            cverts = []
            if len(self.vertices) != 4:
                return cverts
            a, b, c, d = self.vertices
            wallHeight     = d.z*-1 - a.z*-1  ## z height on this wall (sectTop - sectBot)
            nextWallHeight = c.z*-1 - b.z*-1  ## z height on next wall (sectTop - sectBot)
            diffHeight = (wallHeight - nextWallHeight)
            if diffHeight != 0:
                ratio = wallHeight / diffHeight
                clippedVert = Vector(( ((b.x-a.x)*ratio + a.x),   
                                       ((b.y-a.y)*ratio + a.y),
                                       ((b.z-a.z)*ratio + a.z) ))
            if wallHeight > 0:
                cverts.append(a)
                if nextWallHeight > 0:
                    cverts.append(b)
                    cverts.append(c)
                else:
                    cverts.append(clippedVert)
                cverts.append(d)
            else:
                if nextWallHeight > 0:
                    cverts.append(clippedVert)
                    cverts.append(b)
                    cverts.append(c)
                #else: ## skip for walls with no surface.
            return cverts
        
        def isSky(self):
            if self.wallType == self.bmap.WallType.REDBOT:
                return self.wall.sector.getFloor().isParallaxing() and self.neighborSector.getFloor().isParallaxing()
            elif self.wallType == self.bmap.WallType.REDTOP:
                return self.wall.sector.getCeiling().isParallaxing() and self.neighborSector.getCeiling().isParallaxing()
            else:
                return False
        
        def getPicNum(self):
            ## Get picnum, taking swapped textures for bottom walls into account
            neighborWall = self.wall.getNeighborWall()
            if (self.wallType == self.bmap.WallType.REDBOT) and self.wall.getTexBottomSwap() and (neighborWall is not None):
                return neighborWall.data.picnum
            else:
                return self.wall.data.picnum
        
        def getShadeColor(self):
            return self.bmap.calculateShadeColor(self.wall.data.shade)
        
        def getName(self, useIndexInMap=False, prefix=""):
            if self.wallType == self.bmap.WallType.REDBOT:
                return self.wall.getName(useIndexInMap, prefix)+"_Bot"
            elif self.wallType == self.bmap.WallType.REDTOP:
                return self.wall.getName(useIndexInMap, prefix)+"_Top"
            else:
                return self.wall.getName(useIndexInMap, prefix)

class BuildSprite:
    def __init__(self):
        self.data = None
        self.bmap = None
        self.spriteIndex = None
        self.xScal = None
        self.yScal = None
        self.zScal = None
        self.angle = None
        self.designation = None

    def getDesignation(self):
        if self.designation:
            return self.designation
        else:
            lookup_dicts = [
                (game_tile_lookup.DUKE_EFFECT_DICT if not self.bmap.is_blood_map else game_tile_lookup.BLOOD_EFFECT_DICT),
                (game_tile_lookup.DUKE_WEAPON_DICT if not self.bmap.is_blood_map else game_tile_lookup.BLOOD_WEAPON_DICT),
                (game_tile_lookup.DUKE_AMMO_DICT   if not self.bmap.is_blood_map else game_tile_lookup.BLOOD_AMMO_DICT),
                (game_tile_lookup.DUKE_ITEM_DICT   if not self.bmap.is_blood_map else game_tile_lookup.BLOOD_ITEM_DICT),
                (game_tile_lookup.DUKE_ENEMY_DICT  if not self.bmap.is_blood_map else game_tile_lookup.BLOOD_ENEMY_DICT),
            ]
            for lookup_dict in lookup_dicts:
                if self.data.picnum in lookup_dict:
                    return lookup_dict[self.data.picnum]
            return None
    
    def isFlippedX(self):
        ## cstat bit 2: 1 = x-flipped, 0 = normal
        return (self.data.cstat & 4) != 0
    
    def isFlippedY(self):
        ## cstat bit 3: 1 = y-flipped, 0 = normal
        return (self.data.cstat & 8) != 0
    
    def isFaceSprite(self):
        ## cstat bits 5-4: 00 = FACE sprite (default)
        return ((self.data.cstat>>4) & 3) == 0
    
    def isWallSprite(self):
        ## cstat bits 5-4: 01 = WALL sprite (like masked walls)
        return ((self.data.cstat>>4) & 3) == 1
    
    def isFloorSprite(self):
        ## cstat bits 5-4: 10 = FLOOR sprite (parallel to ceilings&floors)
        return ((self.data.cstat>>4) & 3) == 2
    
    def isRealCentered(self):
        ## cstat bit 7: 1 = Real centered centering, 0 = foot center
        return (self.data.cstat & 128) != 0
    
    def getDataKey(self):
        ## This must return a key that is individual for every aspect of a Sprite
        ## that makes it neccessary to have a separate Datablock.
        ## So that when used for a dictionary we can reuse existing datablocks when they make no difference to the sprite.
        return (self.data.picnum, self.isFlippedX(), self.isFlippedY(), self.isFloorSprite(), self.isRealCentered())
    
    def isEffectSprite(self):
        if self.bmap.is_blood_map:
            return self.data.picnum in game_tile_lookup.BLOOD_EFFECT_DICT.keys()
        else:
            return self.data.picnum in game_tile_lookup.DUKE_EFFECT_DICT.keys()
    
    def isWeapon(self):
        if self.bmap.is_blood_map:
            return self.data.picnum in game_tile_lookup.BLOOD_WEAPON_DICT.keys()
        else:
            return self.data.picnum in game_tile_lookup.DUKE_WEAPON_DICT.keys()
    
    def isAmmo(self):
        if self.bmap.is_blood_map:
            return self.data.picnum in game_tile_lookup.BLOOD_AMMO_DICT.keys()
        else:
            return self.data.picnum in game_tile_lookup.DUKE_AMMO_DICT.keys()
    
    def isHealthEquipment(self):
        if self.bmap.is_blood_map:
            return self.data.picnum in game_tile_lookup.BLOOD_ITEM_DICT.keys()
        else:
            return self.data.picnum in game_tile_lookup.DUKE_ITEM_DICT.keys()
    
    def isEnemy(self):
        if self.bmap.is_blood_map:
            return self.data.picnum in game_tile_lookup.BLOOD_ENEMY_DICT.keys()
        else:
            return self.data.picnum in game_tile_lookup.DUKE_ENEMY_DICT.keys()
    
    def getScale(self, like_in_game=True):
        ## Return normalized Scale with 64 as 1
        if self.isFloorSprite():
            scale = ((self.data.yrepeat/64), (self.data.xrepeat/64), (self.data.xrepeat/64))
        else:
            scale = ((self.data.xrepeat/64), (self.data.xrepeat/64), (self.data.yrepeat/64))
        if not self.bmap.is_blood_map and like_in_game and (self.isAmmo() or self.isHealthEquipment()):
            if self.data.picnum == 26:  ## HEAVYHBOMB
                return (0.125, 0.125, 0.125)
            elif self.data.picnum == 40:  ## AMMO
                return (0.25, 0.25, 0.25)
            else:
                return (0.5, 0.5, 0.5)
        else:
            return scale
        
    def getShadeColor(self):
        return self.bmap.calculateShadeColor(self.data.shade)
    
    def getName(self, prefix=""):
        name = f"{prefix}Sprite_{self.spriteIndex:03d}"
        return f"{name}_{self.designation}" if self.designation else name



class IPartParser(ABC):
    @abstractmethod
    def parse(self, mapFile, parentBuildMap, count):
        pass

class BaseSectorParser(IPartParser):
    SECTOR_DATA_NAMES = namedtuple('SectorData', ['wallptr', 'wallnum', 'ceilingz', 'floorz', 'ceilingstat', 'floorstat',
                                                'ceilingpicnum', 'ceilingheinum', 'ceilingshade', 'ceilingpal',
                                                'ceilingxpanning', 'ceilingypanning', 'floorpicnum', 'floorheinum',
                                                'floorshade', 'floorpal', 'floorxpanning', 'floorypanning',
                                                'visibility', 'filler', 'lotag', 'hitag', 'extra'])
    SECTOR_DATA_FORMAT = '<hhii3Hhb3BHhb5B3h'
    @abstractmethod
    def _read_data(self, mapFile, parentBuildMap, index): pass
    
    def __init__(self):
        self.read_size = struct.calcsize(self.SECTOR_DATA_FORMAT)
    
    def parse(self, mapFile: BinaryIO, parentBuildMap: "BuildMapBase", count: int) -> List["BuildSector"]:
        sectors = []
        log.debug(f"{self.__class__.__name__} - Parsing {count} Sectors...")
        for index in range(count):
            new_sect = BuildSector()
            new_sect.data = self._read_data(mapFile, parentBuildMap, index)
            new_sect.bmap        = parentBuildMap
            new_sect.sectorIndex = index
            new_sect.walls       = []
            new_sect.sprites     = []
            new_sect.wallLoops   = []  ## List of list of walls that form loops
            new_sect.zScal       = {}  ## Z-coordinate (height) of floor or ceiling at first point of sector
            new_sect.slopeAbs    = {}
            new_sect.slopeVector = {}  ## slope values (float 1 = 45 degrees)
            new_sect.corrupted   = False
            new_sect.level       = []
            
            for lvl in new_sect.bmap.Level:  ## TODO Refactor this, too
                new_sect.slopeAbs[lvl.name] = 0.0
                new_sect.slopeVector[lvl.name] = Vector((0.0, 0.0))
            if (new_sect.data.floorstat & 2) != 0:
                new_sect.slopeAbs[new_sect.bmap.Level.FLOOR.name] = float(new_sect.data.floorheinum) / 4096
            if (new_sect.data.ceilingstat & 2) != 0:
                new_sect.slopeAbs[new_sect.bmap.Level.CEILING.name] = float(new_sect.data.ceilingheinum) / 4096
            
            for lvl in new_sect.bmap.Level:
                new_sect.level.append(new_sect.SectLevel(new_sect, lvl))
            
            sectors.append(new_sect)
        log.debug(f"{self.__class__.__name__} - Parsed {len(sectors)} Sectors.")
        return sectors

class BaseWallParser(IPartParser):
    WALL_DATA_NAMES = namedtuple('WallData', ['x', 'y', 'point2', 'nextwall', 'nextsector', 'cstat', 'picnum',
                                              'overpicnum', 'shade', 'pal', 'xrepeat', 'yrepeat', 'xpanning',
                                              'ypanning', 'lotag', 'hitag', 'extra'])
    WALL_DATA_FORMAT = '<iiHhh3Hb5B3h'
    @abstractmethod
    def _read_data(self, mapFile, parentBuildMap, index): pass
    
    def __init__(self):
        self.read_size = struct.calcsize(self.WALL_DATA_FORMAT)
    
    def parse(self, mapFile: BinaryIO, parentBuildMap: "BuildMapBase", count: int) -> List["BuildWall"]:
        walls = []
        log.debug(f"{self.__class__.__name__} - Parsing {count} Walls...")
        for indexInMap in range(count):
            new_wall = BuildWall()
            new_wall.data = self._read_data(mapFile, parentBuildMap, indexInMap)
            new_wall.bmap           = parentBuildMap
            new_wall.indexInMap     = indexInMap
            new_wall.indexInSector  = None
            new_wall.sector         = None
            new_wall.xScal          = float(new_wall.data.x) / 512
            new_wall.yScal          = float(new_wall.data.y) / 512
            new_wall.neighborSectorIndex       = -1  ## This has in some cases shown more trustworthy results than relying on the walls nextwall and nextsector fields.
            new_wall.neighborWallIndexInSector = -1  ## This has in some cases shown more trustworthy results than relying on the walls nextwall and nextsector fields.
            new_wall.wallParts: List[BuildWall.WallPart] = []
            
            walls.append(new_wall)
        log.debug(f"{self.__class__.__name__} - Parsed {len(walls)} Walls.")
        return walls

class BaseSpriteParser(IPartParser):
    SPRITE_DATA_NAMES = namedtuple('SpriteData', ['x', 'y', 'z', 'cstat', 'picnum', 'shade', 'pal', 'clipdist', 'filler',
                                                'xrepeat', 'yrepeat', 'xoffset', 'yoffset', 'sectnum', 'statnum', 'ang',
                                                'owner', 'xvel', 'yvel', 'zvel', 'lotag', 'hitag', 'extra'])
    SPRITE_DATA_FORMAT = '<3iHHb5Bbb10h'
    @abstractmethod
    def _read_data(self, mapFile, parentBuildMap, index): pass
    
    def __init__(self):
        self.read_size = struct.calcsize(self.SPRITE_DATA_FORMAT)
    
    def parse(self, mapFile: BinaryIO, parentBuildMap: "BuildMapBase", count: int) -> List["BuildSprite"]:
        sprites = []
        log.debug(f"{self.__class__.__name__} - Parsing {count} Sprites...")
        for index in range(count):
            new_sprite = BuildSprite()
            new_sprite.data = self._read_data(mapFile, parentBuildMap, index)
            new_sprite.bmap        = parentBuildMap
            new_sprite.spriteIndex = index
            new_sprite.xScal       = float(new_sprite.data.x) / 512
            new_sprite.yScal       = float(new_sprite.data.y) / 512
            new_sprite.zScal       = float(new_sprite.data.z) / 8192
            new_sprite.angle       = BuildMapBase.calculateAngle(new_sprite.data.ang)
            new_sprite.designation = new_sprite.getDesignation()
            if 0 <= new_sprite.data.sectnum < new_sprite.bmap.data.numsectors:
                new_sprite.bmap.sectors[new_sprite.data.sectnum].sprites.append(new_sprite)
            else:
                log.warning(f"Sprite {new_sprite.spriteIndex} sectnum is not in range of maps number of sectors: {new_sprite.bmap.data.numsectors}")
            
            sprites.append(new_sprite)
        log.debug(f"{self.__class__.__name__} - Parsed {len(sprites)} Sprites.")
        return sprites


class BuildSectorParser(BaseSectorParser):
    def _read_data(self, mapFile, parentBuildMap, index):
        raw = mapFile.read(self.read_size)
        if len(raw) < self.read_size:
            parentBuildMap.handleError(ignorable=False, errorMsg="Unexpected end of file while reading data block")
        return self.SECTOR_DATA_NAMES._make(struct.unpack(self.SECTOR_DATA_FORMAT, raw))

class BuildWallParser(BaseWallParser):
    def _read_data(self, mapFile, parentBuildMap, index):
        raw = mapFile.read(self.read_size)
        if len(raw) < self.read_size:
            parentBuildMap.handleError(ignorable=False, errorMsg="Unexpected end of file while reading data block")
        return self.WALL_DATA_NAMES._make(struct.unpack(self.WALL_DATA_FORMAT, raw))

class BuildSpriteParser(BaseSpriteParser):
    def _read_data(self, mapFile, parentBuildMap, index):
        raw = mapFile.read(self.read_size)
        if len(raw) < self.read_size:
            parentBuildMap.handleError(ignorable=False, errorMsg="Unexpected end of file while reading data block")
        return self.SPRITE_DATA_NAMES._make(struct.unpack(self.SPRITE_DATA_FORMAT, raw))


class BloodSectorParser(BaseSectorParser):
    def __init__(self):
        super().__init__()
        self.sectorBloodDataSize = 60  ## Size of additional Blood-DataBlock that might be appended to the regular Build-SectorData
    def _read_data(self, mapFile, parentBuildMap, index):
        key = (parentBuildMap.data.revisions * 40) & 0xFF
        raw = bytearray(mapFile.read(self.read_size))
        if len(raw) < self.read_size:
            parentBuildMap.handleError(ignorable=False, errorMsg="Unexpected end of file while reading data block")
        parentBuildMap.decrypt_block(raw, key, key_increment=0)
        data = self.SECTOR_DATA_NAMES._make(struct.unpack(self.SECTOR_DATA_FORMAT, raw))
        if data.extra > 0:
            log.debug(f"Sector {index}: tag-extra={data.extra} Skipping additional Blood Sector Data.")
            mapFile.seek(self.sectorBloodDataSize, os.SEEK_CUR)
        return data

class BloodWallParser(BaseWallParser):
    def __init__(self):
        super().__init__()
        self.wallBloodDataSize = 24  ## Size of additional Blood-DataBlock that might be appended to the regular Build-WallData
    def _read_data(self, mapFile, parentBuildMap, index):
        key = ((parentBuildMap.data.revisions * 40) | 0x4D) & 0xFF
        raw = bytearray(mapFile.read(self.read_size))
        if len(raw) < self.read_size:
            parentBuildMap.handleError(ignorable=False, errorMsg="Unexpected end of file while reading data block")
        parentBuildMap.decrypt_block(raw, key, key_increment=0)
        data = self.WALL_DATA_NAMES._make(struct.unpack(self.WALL_DATA_FORMAT, raw))
        if data.extra > 0:
            log.debug(f"Wall {index}: tag-extra={data.extra} Skipping additional Blood Wall Data.")
            mapFile.seek(self.wallBloodDataSize, os.SEEK_CUR)
        return data

class BloodSpriteParser(BaseSpriteParser):
    def __init__(self):
        super().__init__()
        self.spriteBloodDataSize = 56  ## Size of additional Blood-DataBlock that might be appended to the regular Build-SpriteData
    def _read_data(self, mapFile, parentBuildMap, index):
        key = ((parentBuildMap.data.revisions * 44) | 0x4D) & 0xFF
        raw = bytearray(mapFile.read(self.read_size))
        if len(raw) < self.read_size:
            parentBuildMap.handleError(ignorable=False, errorMsg="Unexpected end of file while reading data block")
        parentBuildMap.decrypt_block(raw, key, key_increment=0)
        data = self.SPRITE_DATA_NAMES._make(struct.unpack(self.SPRITE_DATA_FORMAT, raw))
        if data.extra > 0:
            log.debug(f"Sprite {index}: tag-extra={data.extra} Skipping additional Blood Sprite Data.")
            mapFile.seek(self.spriteBloodDataSize, os.SEEK_CUR)
        return data



class BuildMapBase(ABC):
    
    class Level(Enum):
        FLOOR   = 0
        CEILING = 1
    
    class WallType(Enum):
        WHITE  = 0  ## simple "white wall" (wall that is not connecting to another sector)
        REDBOT = 1  ## bottom portion of "red wall" (bottom portion of wall that is connecting to another sector)
        REDTOP = 2  ## top portion of "red wall" (top portion of wall that is connecting to another sector)
    
    class _MapData:
        def __init__(self):
            self.magic       = None
            self.mapversion_major = None
            self.posx        = None
            self.posy        = None
            self.posz        = None
            self.ang         = None
            self.cursectnum  = None
            self.numsectors  = None
            self.numwalls    = None
            self.numsprites  = None
            ## Additional Blood Map Data:
            self.mapversion_minor = None
            self.flags       = None
            self.unknown5s   = None
            self.matt_string = None
            self.unknown2    = None  ## Possibly Sky- or Parallax-Type?
            self.revisions   = None
            self.copyright   = None
            self.xsprite     = None
            self.xwall       = None
            self.xsector     = None
            self.sky_entry_count = None
            self.sky_offsets = None
    
    def __init__(self, mapFilePath, heuristicWallSearch=False, ignoreErrors=False):
        self.mapFilePath = mapFilePath
        self.heuristicWallSearch = heuristicWallSearch
        self.ignoreErrors = ignoreErrors
        if not isinstance(self.mapFilePath, str) or not os.path.isfile(self.mapFilePath):
            self.handleError(ignorable=False, errorMsg=f"File not found: {self.mapFilePath}")
            return
        
        self.mapFileSize = os.path.getsize(self.mapFilePath)
        log.debug(f"Opening file ({self.mapFileSize} Bytes): {self.mapFilePath}")
        self.readMapFile()
        log.debug(f"Map Type: {'Blood' if self.is_blood_map else 'Build'}")
        log.debug(f"TROR Supported: {self.tror_supported}")
        

        self.posxScal = float(self.data.posx) / 512
        self.posyScal = float(self.data.posy) / 512
        self.poszScal = float(self.data.posz) / 8192

        ## Find Wall Loops
        log.debug("Start Finding Wall Loops")
        for sect in self.sectors:
            sectorWallLastIdx = sect.data.wallptr+sect.data.wallnum-1
            while len(sect.walls) < sect.data.wallnum:
                wallLoop = []
                if len(sect.walls) == 0:
                    ## First loop starts with sect.data.wallptr
                    firstWallInLoop = self.getWall(sect.data.wallptr)
                    if firstWallInLoop is None:
                        sect.corrupted = True
                        self.handleError(ignorable=True, errorMsg=f"Unable to find next wall for first loop for sector {sect.sectorIndex}")
                        break
                else:
                    ## To find the first wall of the next loop,
                    ## search for the next wall that is not yet assigned
                    ## starting from the Sectors first wall.
                    findNextIdx = sect.data.wallptr
                    while True:
                        wall = self.getWall(findNextIdx)
                        if wall is None:
                            sect.corrupted = True
                            self.handleError(ignorable=True, errorMsg=f"Unable to find next wall for next loop for sector {sect.sectorIndex}")
                            break
                        if wall not in sect.walls:
                            firstWallInLoop = wall
                            break
                        findNextIdx += 1
                if sect.corrupted:
                    break
                ## Create the next wall loop
                currentWall = firstWallInLoop
                while True:
                    sect.walls.append(currentWall)
                    wallLoop.append(currentWall)
                    if (currentWall.data.point2 < sect.data.wallptr) or (currentWall.data.point2 > sectorWallLastIdx):
                        sect.corrupted = True
                        self.handleError(ignorable=True, errorMsg=f"Wall loop extends outside sectors range! wall.data.point2 {currentWall.data.point2} not in range of sector walls! {sect.data.wallptr} to {sectorWallLastIdx} for sector {sect.sectorIndex}")
                    currentWall = self.getWall(currentWall.data.point2)
                    if (currentWall is None) or (currentWall in wallLoop) or ((not self.ignoreErrors) and (len(sect.walls) >= sect.data.wallnum)):
                        if currentWall is None:
                            sect.corrupted = True
                            self.handleError(ignorable=True, errorMsg=f"Unable to find next wall for loop of sector {sect.sectorIndex} ! Wall is outside of map range.")
                        elif currentWall != firstWallInLoop:
                            sect.corrupted = True
                            self.handleError(ignorable=True, errorMsg=f"Wall Loop did not end on first wall in loop in sector {sect.sectorIndex} !")
                        if len(sect.walls) > sect.data.wallnum:
                            sect.corrupted = True
                            log.error(f"Walls in loop exceed number of walls in sector {sect.sectorIndex} !")
                        break
                sect.wallLoops.append(wallLoop)
        log.debug("Finished Finding Wall Loops")

        ## Link Walls to Sectors
        for sect in self.getSectors():
            wallIndexInSect = 0
            for loop in sect.wallLoops:
                for wall in loop:
                    wall.indexInSector = wallIndexInSect
                    wall.sector = sect
                    wallIndexInSect += 1

        ## Postprocessing: Find wall and sector neighbors of walls
        if self.heuristicWallSearch:
            self.find_wall_neighbors_heuristic()
        else:
            self.find_wall_neighbors_by_index()

        ## Postprocessing: Calculate Wall vectors and angles with now known basic properties
        for wall in self.walls:
            if (wall.sector is None) or (wall.sector.corrupted):
                log.warning(f"Wall {wall.indexInMap} is not used or sector is corrupted!")
            else:
                wall.finalize()

        ## Postprocessing: Calculate slope for x and y directions separately
        for sect in self.getSectors():
            for lvl in self.Level:
                sect.slopeVector[lvl.name] = Vector(((math.sin(sect.walls[0].angle) * sect.slopeAbs[lvl.name]),
                                                     (math.cos(sect.walls[0].angle) * -1 * sect.slopeAbs[lvl.name])))

        log.debug(f"Finished parsing file: {self.mapFilePath}")

    @abstractmethod
    def _validate(self, mapFile): pass
    
    @abstractmethod
    def _read_header(self, mapFile): pass

    @abstractmethod
    def _read_sectors(self, mapFile): pass

    @abstractmethod
    def _read_walls(self, mapFile): pass

    @abstractmethod
    def _read_sprites(self, mapFile): pass
    
    @abstractmethod
    def _read_trailer(self, mapFile): pass

    def readMapFile(self):
        with open(self.mapFilePath, "rb") as mapFile:
            self.data = BuildMapBase._MapData()
            self.sectors: List[BuildSector] = []
            self.walls:   List[BuildWall]   = []
            self.sprites: List[BuildSprite] = []
            self.is_blood_map = None
            self.tror_supported = None
            
            self._validate(mapFile)
            self._read_header(mapFile)
            self._read_sectors(mapFile)
            self._read_walls(mapFile)
            
            ## Sanity Check: Number of walls in Sectors has to match absolute number of walls
            numberOfWallsInAllSectors = sum(map(lambda s: s.data.wallnum, self.sectors))
            
            if numberOfWallsInAllSectors != self.data.numwalls:
                self.handleError(ignorable=True,
                                 errorMsg=f"Number of walls found in Sectors {numberOfWallsInAllSectors} does not match given absolute number of walls: {self.data.numwalls} !")
            
            self._read_sprites(mapFile)
            self._read_trailer(mapFile)

    def getWallListString(self, wall_list):
        return "; ".join([wall.getName() for wall in wall_list])
    
    def find_wall_neighbors_heuristic(self):
        ## Find wall and sector neighbors of walls using Coordinates.
        ## This has in some cases shown more trustworthy results than relying on the walls nextwall and nextsector fields.
        ## This can be improved by taking z coordinates into account as a step to support TROR
        walls_dict = {}
        for wall in self.getWalls():
            point2Wall = wall.getPoint2Wall()
            if point2Wall is not None:
                key = tuple(sorted([(wall.data.x, wall.data.y), (point2Wall.data.x, point2Wall.data.y)]))
                if walls_dict.get(key) is None:
                    walls_dict[key] = []
                walls_dict[key].append(wall)
        for wall_list in walls_dict.values():
            if len(wall_list) < 2:
                continue  ## This wall has no neighbors
            if (self.tror_supported == False) and (len(wall_list) > 2):
                log.warning(f"More than 2 neighboring walls found in non-TROR map: {self.getWallListString(wall_list)}")
            if wall_list[0].sector.sectorIndex == wall_list[1].sector.sectorIndex:
                log.warning(f"Two walls in same sector found with same coordinates: {self.getWallListString(wall_list)}")
                continue  ## Walls in the same sector can't be neighbors!
            wall_list[0].neighborSectorIndex       = wall_list[1].sector.sectorIndex
            wall_list[0].neighborWallIndexInSector = wall_list[1].indexInSector
            wall_list[1].neighborSectorIndex       = wall_list[0].sector.sectorIndex
            wall_list[1].neighborWallIndexInSector = wall_list[0].indexInSector
    
    def find_wall_neighbors_by_index(self):
        for wall in self.getWalls():
            if (wall.data.nextwall >= 0) and (wall.data.nextsector >= 0) and (wall.data.nextwall < self.data.numwalls) and (wall.data.nextsector < self.data.numsectors):
                wall.neighborSectorIndex = wall.data.nextsector
                wall.neighborWallIndexInSector = self.walls[wall.data.nextwall].indexInSector
    
    @staticmethod
    def calculateAngle(buildAngle):
        return ((float(buildAngle) * math.pi) / 1024) * -1  ## 2048 = 360 deg = 2 PI
    
    def getSectors(self):
        return [sect for sect in self.sectors if not sect.corrupted]
    
    def getWall(self, index):
        if (index < 0) or (index >= len(self.walls)):
            return None
        return self.walls[index]
    
    def getWalls(self):
        return [wall for wall in self.walls if
                ((wall.sector is not None) and (not wall.sector.corrupted) and (wall.getPoint2Wall() is not None))]
    
    def handleError(self, ignorable=False, errorMsg="Unknown Error!"):
        log.error(errorMsg)
        if (not ignorable) or (not self.ignoreErrors):
            raise ValueError(errorMsg)
    
    def calculateShadeColor(self, shade):
        ## observed shade values for Duke Nukem 3D: -128, -50, -5, 0 to 30
        ## observed shade values for Blood: -128, -8, 0 to 63
        max_shade_in  = 30 if not self.is_blood_map else 63
        min_shade_out = 0.0 if not self.is_blood_map else 0.1
        if shade <= 0:
            return (1.0, 1.0, 1.0, 1.0)
        if shade >= max_shade_in:
            return (min_shade_out, min_shade_out, min_shade_out, 1.0)
        
        if self.is_blood_map:
            if shade <= 0:
                v = 1.0
            else:
                shade_intensity_ratio = min(shade, max_shade_in) / max_shade_in
                v = 1.0 - ((1.0 - min_shade_out) * shade_intensity_ratio)
            return (v, v, v, 1.0)
        else:
            r = -(0.000432*shade*shade) -(0.021012*shade) + (0.986183)
            g = -(0.000256*shade*shade) -(0.025906*shade) + (0.980335)
            b = -(0.000288*shade*shade) -(0.025329*shade) + (0.991496)
            return (r, g, b, 1.0)
    
    def get_required_picnums(self, include_overpic=True):
        required_picnums = set()
        for sect in self.getSectors():
            required_picnums.add(int(sect.data.floorpicnum))
            required_picnums.add(int(sect.data.ceilingpicnum))
        for wall in self.getWalls():
            required_picnums.add(int(wall.data.picnum))
            if include_overpic:
                required_picnums.add(int(wall.data.overpicnum))
        for sprt in self.sprites:
            required_picnums.add(int(sprt.data.picnum))
        return sorted(n for n in required_picnums if n >= 0)



class BuildMap(BuildMapBase):
    MAGIC_SIGNATURES = [b"\x03\x00\x00\x00", b"\x04\x00\x00\x00", b"\x05\x00\x00\x00", b"\x06\x00\x00\x00", b"\x07\x00\x00\x00", b"\x08\x00\x00\x00", b"\x09\x00\x00\x00"]
    SUPPORTED_VERSIONS = [7, 8, 9]
    
    def _validate(self, mapFile):
        self.data.magic = mapFile.read(4)
        if self.data.magic not in self.MAGIC_SIGNATURES:
            self.handleError(ignorable=False, errorMsg=f"Unknown File Format starting with: 0x{self.data.magic.hex().upper()}")
            return
        self.data.mapversion_major = struct.unpack('<i', self.data.magic)[0]
        self.data.mapversion_minor = None
        if self.data.mapversion_major not in self.SUPPORTED_VERSIONS:
            self.handleError(ignorable=False, errorMsg=f"Unsupported file version {self.data.mapversion_major}! Only BUILD Maps in version 7, 8 and 9 are supported.")
            return
        log.debug(f"mapversion_major: {self.data.mapversion_major}  mapversion_minor: {self.data.mapversion_minor}.")
        self.is_blood_map = False
        self.tror_supported = True if (self.data.mapversion_major >= 9) else False
        return

    def _read_header(self, mapFile):
        self.data.posx = struct.unpack('<i', mapFile.read(4))[0]
        self.data.posy = struct.unpack('<i', mapFile.read(4))[0]
        self.data.posz = struct.unpack('<i', mapFile.read(4))[0]
        self.data.ang = struct.unpack('<h', mapFile.read(2))[0]
        self.data.cursectnum = struct.unpack('<h', mapFile.read(2))[0]
        self.spawnAngle = BuildMapBase.calculateAngle(self.data.ang)
        log.debug(f"posx: {self.data.posx}")
        log.debug(f"posy: {self.data.posy}")
        log.debug(f"posz: {self.data.posz}")
        log.debug(f"ang: {self.data.ang}")
        log.debug(f"spawnAngle: {self.spawnAngle}")
        log.debug(f"cursectnum: {self.data.cursectnum}")

    def _read_sectors(self, mapFile):
        self.data.numsectors = struct.unpack('<H', mapFile.read(2))[0]
        log.debug(f"numsectors: {self.data.numsectors}")
        sect_parser = BuildSectorParser()
        self.sectors = sect_parser.parse(mapFile, self, self.data.numsectors)

    def _read_walls(self, mapFile):
        self.data.numwalls = struct.unpack('<H', mapFile.read(2))[0]
        log.debug(f"numwalls: {self.data.numwalls}")
        wall_parser = BuildWallParser()
        self.walls = wall_parser.parse(mapFile, self, self.data.numwalls)

    def _read_sprites(self, mapFile):
        self.data.numsprites = struct.unpack('<H', mapFile.read(2))[0]
        log.debug(f"numsprites: {self.data.numsprites}")
        sprite_parser = BuildSpriteParser()
        self.sprites = sprite_parser.parse(mapFile, self, self.data.numsprites)
    
    def _read_trailer(self, mapFile):
        filepos = mapFile.tell()
        log.debug(f"Finishing file parsing. Map file size: {self.mapFileSize} Current file position: {filepos}")
        log.debug(("EOF reached." if filepos == self.mapFileSize else "EOF not reached!"))


class BuildMapBlood(BuildMapBase):
    MAGIC_SIGNATURES = [b"BLM\x1A"]
    SUPPORTED_VERSIONS = [(7,0)]
    
    def decrypt_block(self, buf: bytearray, key: int, key_increment: int = 0) -> int:
        n = len(buf)
        for i in range(n):
            buf[i] ^= (key + key_increment + i) & 0xFF
        return key_increment + n
    
    def _validate(self, mapFile):
        self.data.magic = mapFile.read(4)
        if self.data.magic not in self.MAGIC_SIGNATURES:
            self.handleError(ignorable=False, errorMsg=f"Unknown File Format starting with: 0x{self.data.magic.hex().upper()}")
            return
        self.data.mapversion_minor = struct.unpack('B', mapFile.read(1))[0]
        self.data.mapversion_major = struct.unpack('B', mapFile.read(1))[0]
        encrypted = True if (self.data.mapversion_major == 7 and self.data.mapversion_minor == 0) else False
        if (self.data.mapversion_major, self.data.mapversion_minor) not in self.SUPPORTED_VERSIONS:
            self.handleError(ignorable=False, errorMsg=f"Detected Blood Map Format v{self.data.mapversion_major}.{self.data.mapversion_minor}{' (encrypted)' if encrypted else ''}. This is not yet supported!")
        log.debug(f"mapversion_major: {self.data.mapversion_major}  mapversion_minor: {self.data.mapversion_minor}{' (encrypted)' if encrypted else ''}.")
        self.is_blood_map = True
        self.tror_supported = True
        return
    
    def _read_header(self, mapFile):
        key_increment = 0
        key = 0x4D
        
        ## Header1
        header1_data_names = namedtuple('Header1Data', ['posx', 'posy', 'posz', 'ang', 'cursectnum'])
        header1_data_format = '<3ihh'
        log.debug("=== Header 1 ===")
        
        raw = bytearray(mapFile.read(struct.calcsize(header1_data_format)))
        key_increment = self.decrypt_block(raw, key, key_increment)
        header1_data = header1_data_names._make(struct.unpack(header1_data_format, raw))
        
        self.data.posx = header1_data.posx
        self.data.posy = header1_data.posy
        self.data.posz = header1_data.posz
        self.data.ang  = header1_data.ang
        self.data.cursectnum = header1_data.cursectnum
        self.spawnAngle = BuildMapBase.calculateAngle(self.data.ang)
        log.debug(f"posx: {self.data.posx}")
        log.debug(f"posy: {self.data.posy}")
        log.debug(f"posz: {self.data.posz}")
        log.debug(f"ang: {self.data.ang}")
        log.debug(f"spawnAngle: {self.spawnAngle}")
        log.debug(f"cursectnum: {self.data.cursectnum}")
        
        ## Header2
        header2_data_names = namedtuple('Header2Data', ['flags', 'unknown5s', 'matt_string', 'unknown2'])
        header2_data_format = '<B5s4sB'
        log.debug("=== Header 2 ===")
        
        raw = bytearray(mapFile.read(struct.calcsize(header2_data_format)))
        key_increment = self.decrypt_block(raw, key, key_increment)
        header2_data = header2_data_names._make(struct.unpack(header2_data_format, raw))
        
        self.data.flags       = header2_data.flags
        self.data.unknown5s   = header2_data.unknown5s
        self.data.matt_string = header2_data.matt_string.decode('ascii', errors='replace')
        self.data.unknown2    = header2_data.unknown2
        
        unk2bits = self.data.flags & 0x03
        has_sky  = (self.data.flags >> 2) & 0x01
        unk5bits = (self.data.flags >> 3) & 0x1F
        
        log.debug(f"flags:       unk2bits=0b{unk2bits:02b}, has_sky={has_sky}, unk5bits=0b{unk5bits:05b}")
        log.debug(f"unknown5s:   {self.data.unknown5s}")
        log.debug(f"matt_string: {self.data.matt_string!r}")
        log.debug(f"unknown2:    {self.data.unknown2}")
        
        ## Header3
        header3_data_names = namedtuple('Header3Data', ['revisions', 'sector_count', 'wall_count', 'sprite_count'])
        header3_data_format = '<IHHH'
        log.debug("=== Header 3 ===")
        
        raw = bytearray(mapFile.read(struct.calcsize(header3_data_format)))
        key_increment = self.decrypt_block(raw, key, key_increment)
        header3_data = header3_data_names._make(struct.unpack(header3_data_format, raw))
        
        self.data.revisions  = header3_data.revisions
        self.data.numsectors = header3_data.sector_count
        self.data.numwalls   = header3_data.wall_count
        self.data.numsprites = header3_data.sprite_count
        log.debug(f"revisions: {self.data.revisions}")
        log.debug(f"numsectors: {self.data.numsectors}")
        log.debug(f"numwalls: {self.data.numwalls}")
        log.debug(f"numsprites: {self.data.numsprites}")
        
        ## Header4
        key_increment = 0
        key = self.data.numwalls & 0xFF
        header4_data_names = namedtuple('Header4Data', ['copyright', 'reserved7s', 'xsprite', 'xwall', 'xsector', 'reserved52s'])
        header4_data_format = '<57s7sIII52s'
        log.debug("=== Header 4 ===")
        
        raw = bytearray(mapFile.read(struct.calcsize(header4_data_format)))
        key_increment = self.decrypt_block(raw, key, key_increment)
        header4_data = header4_data_names._make(struct.unpack(header4_data_format, raw))
        
        self.data.copyright = header4_data.copyright.decode('ascii', errors='replace').rstrip("\x00")
        self.data.xsprite   = header4_data.xsprite
        self.data.xwall     = header4_data.xwall
        self.data.xsector   = header4_data.xsector
        log.info(f"Copyright String: {self.data.copyright}")
        log.debug(f"reserved7s: {header4_data.reserved7s}")
        log.debug(f"xsprite: {self.data.xsprite}")
        log.debug(f"xwall:   {self.data.xwall}")
        log.debug(f"xsector: {self.data.xsector}")
        log.debug(f"reserved52s: {header4_data.reserved52s}")
        
        ## Sky Offsets
        log.debug("=== Sky Offsets ===")
        sky_offset_block_size = struct.unpack('<B', mapFile.read(1))[0]
        sky_offset_unknown    = struct.unpack('<B', mapFile.read(1))[0] ^ 1
        self.data.sky_entry_count = sky_offset_block_size // 2
        log.debug(f"sky_offset_block_size: {sky_offset_block_size}")
        log.debug(f"sky_offset_unknown:    {sky_offset_unknown}")
        log.debug(f"sky_entry_count:       {self.data.sky_entry_count}")
        if has_sky:
            mapFile.seek(-2, 1)
            log.debug(f"Parsing {self.data.sky_entry_count} Sky-Offsets Entries")
            raw = bytearray(mapFile.read(sky_offset_block_size))
            key_increment = self.decrypt_block(raw, key=sky_offset_block_size, key_increment=0)
            self.data.sky_offsets = list(struct.unpack(f"<{self.data.sky_entry_count}h", raw))
            log.debug(f"Sky-Offsets: {self.data.sky_offsets}")

    def _read_sectors(self, mapFile):
        sect_parser = BloodSectorParser()
        self.sectors = sect_parser.parse(mapFile, self, self.data.numsectors)

    def _read_walls(self, mapFile):
        wall_parser = BloodWallParser()
        self.walls = wall_parser.parse(mapFile, self, self.data.numwalls)

    def _read_sprites(self, mapFile):
        sprite_parser = BloodSpriteParser()
        self.sprites = sprite_parser.parse(mapFile, self, self.data.numsprites)
    
    def _read_trailer(self, mapFile):
        filepos = mapFile.tell()
        log.debug(f"Finishing file parsing. Map file size: {self.mapFileSize} Current file position: {filepos}")
        crcDataFormat = '<I'
        crcSize = struct.calcsize(crcDataFormat)
        if filepos + crcSize <= self.mapFileSize:
            raw = mapFile.read(crcSize)
            crc = struct.unpack(crcDataFormat, raw)[0]
            log.debug(f"CRC at Offset={filepos}: 0x{crc:08X}")
        else:
            log.debug(f"No CRC found (EOF reached)")



def BuildMapFactory(mapFilePath: str, heuristicWallSearch: bool, ignoreErrors: bool) -> BuildMapBase:
    with open(mapFilePath, 'rb') as f:
        magic = f.read(4)
    if magic in BuildMap.MAGIC_SIGNATURES:
        log.debug(f"BuildMapFactory - Detected Build Map File with magic: 0x{magic.hex().upper()}")
        return BuildMap(mapFilePath, heuristicWallSearch, ignoreErrors)
    elif magic in BuildMapBlood.MAGIC_SIGNATURES:
        log.debug(f"BuildMapFactory - Detected Blood Map File with magic: {magic}")
        return BuildMapBlood(mapFilePath, heuristicWallSearch, ignoreErrors)
    else:
        errorMsg = f"Unknown File Format starting with: 0x{magic.hex().upper()}"
        log.error(errorMsg)
        raise ValueError(errorMsg)


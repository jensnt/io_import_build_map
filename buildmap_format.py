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



import logging
import math
import os
import struct
from collections import namedtuple
from enum import Enum
from typing import List

from mathutils import Vector

log = logging.getLogger(__name__)



class BuildMap:
    
    class Level(Enum):
        FLOOR = 0
        CEILING = 1
    
    class WallType(Enum):
        WHITE = 0   ## simple white wall (wall that is not connecting to another sector)
        REDBOT = 1  ## bottom portion of red wall (bottom portion of wall that is connecting to another sector)
        REDTOP = 2  ## top portion of red wall (top portion of wall that is connecting to another sector)
    
    class _MapData:
        def __init__(self):
            self.mapversion = None
            self.posx       = None
            self.posy       = None
            self.posz       = None
            self.ang        = None
            self.cursectnum = None
            self.numsectors = None
            self.numwalls   = None
            self.numsprites = None
    
    def __init__(self, mapFilePath, ignoreErrors=False):
        self.ignoreErrors = ignoreErrors
        if not isinstance(mapFilePath, str) or not os.path.isfile(mapFilePath):
            self.handleError(ignorable=False, errorMsg="File not found: %s" % mapFilePath)
            return

        log.debug("Opening file: %s" % mapFilePath)
        self.readMapFile(mapFilePath)


        self.posxScal = float(self.data.posx) / 512
        self.posyScal = float(self.data.posy) / 512
        self.poszScal = float(self.data.posz) / 8192

        ## Find Wall Loops
        log.debug("Start Finding Wall Loops")
        for sect in self.sectors:
            sectorWallLastIdx = sect.data.wallptr+sect.data.wallnum-1
            while len(sect.walls) < sect.data.wallnum:
                wallLoop = list()
                if len(sect.walls) == 0:
                    ## First loop starts with sect.data.wallptr
                    firstWallInLoop = self.getWall(sect.data.wallptr)
                    if firstWallInLoop is None:
                        sect.corrupted = True
                        self.handleError(ignorable=True, errorMsg="Unable to find next wall for first loop for sector %s" % sect.sectorIndex)
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
                            self.handleError(ignorable=True, errorMsg="Unable to find next wall for next loop for sector %s" % sect.sectorIndex)
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
                        self.handleError(ignorable=True, errorMsg="Wall loop extends outside sectors range! wall.data.point2 %s not in range of sector walls! %s to %s for sector %s" % (currentWall.data.point2, sect.data.wallptr, sectorWallLastIdx, sect.sectorIndex))
                    currentWall = self.getWall(currentWall.data.point2)
                    if (currentWall is None) or (currentWall in wallLoop) or ((not self.ignoreErrors) and (len(sect.walls) >= sect.data.wallnum)):
                        if currentWall is None:
                            sect.corrupted = True
                            self.handleError(ignorable=True, errorMsg="Unable to find next wall for loop of sector %s ! Wall is outside of map range." % sect.sectorIndex)
                        elif currentWall != firstWallInLoop:
                            sect.corrupted = True
                            self.handleError(ignorable=True, errorMsg="Wall Loop did not end on first wall in loop in sector %s !" % sect.sectorIndex)
                        if len(sect.walls) > sect.data.wallnum:
                            sect.corrupted = True
                            log.error("Walls in loop exceed number of walls in sector %s !" % sect.sectorIndex)
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
        self.find_wall_neighbors()

        ## Postprocessing: Calculate Wall vectors and angles with now known basic properties
        for wall in self.walls:
            if (wall.sector is None) or (wall.sector.corrupted):
                log.warning("Wall %s is not used or sector is corrupted!" % wall.indexInMap)
            else:
                wall.__post_init__()

        ## Postprocessing: Calculate slope for x and y directions separately
        for sect in self.getSectors():
            for lvl in self.Level:
                sect.slopeVector[lvl.name] = Vector(((math.sin(sect.walls[0].angle) * sect.slopeAbs[lvl.name]),
                                                     (math.cos(sect.walls[0].angle) * -1 * sect.slopeAbs[lvl.name])))

        log.debug("Finished parsing file: %s" % mapFilePath)

    def readMapFile(self, mapFilePath):
        with open(mapFilePath, "rb") as mapFile:
            self.data = BuildMap._MapData()
            self.data.mapversion = struct.unpack('<i', mapFile.read(4))[0]
            if self.data.mapversion not in [7, 8, 9]:
                self.handleError(ignorable=False, errorMsg="Unsupported file! Only BUILD Maps in version 7, 8 and 9 are supported.")
                return

            self.data.posx = struct.unpack('<i', mapFile.read(4))[0]
            self.data.posy = struct.unpack('<i', mapFile.read(4))[0]
            self.data.posz = struct.unpack('<i', mapFile.read(4))[0]
            self.data.ang = struct.unpack('<h', mapFile.read(2))[0]
            self.data.cursectnum = struct.unpack('<h', mapFile.read(2))[0]
            self.data.numsectors = struct.unpack('<H', mapFile.read(2))[0]
            self.sectors: List[BuildMap.BuildSector] = list()
            self.walls:   List[BuildMap.BuildWall]   = list()
            self.sprites: List[BuildMap.BuildSprite] = list()

            log.debug("mapversion: %s" % self.data.mapversion)
            log.debug("posx: %s" % self.data.posx)
            log.debug("posy: %s" % self.data.posy)
            log.debug("posz: %s" % self.data.posz)
            log.debug("ang: %s" % self.data.ang)
            log.debug("cursectnum: %s" % self.data.cursectnum)
            log.debug("numsectors: %s" % self.data.numsectors)

            self.spawnAngle = BuildMap.calculateAngle(self.data.ang)

            ## Read Sectors
            for i in range(self.data.numsectors):
                self.sectors.append(self.BuildSector(mapFile, self, i))
            self.data.numwalls = struct.unpack('<H', mapFile.read(2))[0]
            log.debug("numwalls: %s" % self.data.numwalls)

            ## Sanity Check: Number of walls in Secors has to match absolute number of walls
            numberOfWallsInAllSectors = sum(map(lambda s: s.data.wallnum, self.sectors))

            if numberOfWallsInAllSectors != self.data.numwalls:
                self.handleError(ignorable=True,
                                 errorMsg="Number of walls found in Sectors %s does not match given absolute number of walls: %s !" % (
                                     numberOfWallsInAllSectors, self.data.numwalls))

            ## Read Walls
            for i in range(self.data.numwalls):
                self.walls.append(self.BuildWall(mapFile, self, i))
            ## Read Sprites
            self.data.numsprites = struct.unpack('<H', mapFile.read(2))[0]
            log.debug("numsprites: %s" % self.data.numsprites)
            for i in range(self.data.numsprites):
                self.sprites.append(self.BuildSprite(mapFile, self, i))

    def getWallListString(self, wall_list):
        return "; ".join([wall.getName() for wall in wall_list])
    
    def find_wall_neighbors(self):  ## TODO I think neighbors are wrongly detected with TROR! This needs to be sorted out FIRST before thinking of any other ideas how to fix Walls with TROR
        ## Find wall and sector neighbors of walls using Coordinates.
        ## This has in some cases shown more trustworthy results than relying on the walls nextwall and nextsector fields.
        ## This can be improved by taking z coordinates into account as a step to support TROR
        walls_dict = dict()
        for wall in self.getWalls():
            nextWall = wall.getPoint2Wall()
            if nextWall is not None:
                key = tuple(sorted([(wall.data.x, wall.data.y), (nextWall.data.x, nextWall.data.y)]))
                if walls_dict.get(key) is None:
                    walls_dict[key] = list()
                walls_dict[key].append(wall)
        for wall_list in walls_dict.values():
            if len(wall_list) < 2:
                continue  ## This wall has no neighbors
            if len(wall_list) > 2:
                log.warning("More than 2 neighboring walls found: %s" % self.getWallListString(wall_list))
            if wall_list[0].sector.sectorIndex == wall_list[1].sector.sectorIndex:
                log.warning("Two walls in same sector found with same coordinates: %s" % self.getWallListString(wall_list))
                continue  ## Walls in the same sector can't be neighbors!
            wall_list[0].neighborSectorIndex       = wall_list[1].sector.sectorIndex
            wall_list[0].neighborWallIndexInSector = wall_list[1].indexInSector
            wall_list[1].neighborSectorIndex       = wall_list[0].sector.sectorIndex
            wall_list[1].neighborWallIndexInSector = wall_list[0].indexInSector
    
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
    
    
    class BuildSector:
        sectorDataNames = namedtuple('SectorData', ['wallptr', 'wallnum', 'ceilingz', 'floorz', 'ceilingstat', 'floorstat',
                                                    'ceilingpicnum', 'ceilingheinum', 'ceilingshade', 'ceilingpal',
                                                    'ceilingxpanning', 'ceilingypanning', 'floorpicnum', 'floorheinum',
                                                    'floorshade', 'floorpal', 'floorxpanning', 'floorypanning',
                                                    'visibility', 'filler', 'lotag', 'hitag', 'extra'])
        sectorDataFormat = '<hhii4hbBBBhhb5Bhhh'
        def __init__(self, mapFile, parentBuildMap, index):
            raw = mapFile.read(struct.calcsize(self.sectorDataFormat))
            self.data = self.sectorDataNames._make(struct.unpack(self.sectorDataFormat, raw))
            
            self.bmap            = parentBuildMap
            self.sectorIndex     = index
            self.walls:   List[BuildMap.BuildWall]   = list()
            self.sprites: List[BuildMap.BuildSprite] = list()
            self.wallLoops       = list()  ## List of list of walls that form loops
            self.zScal           = dict()  ## Z-coordinate (height) of floor or ceiling at first point of sector
            self.slopeAbs        = dict()
            self.slopeVector     = dict()  ## slope values (float 1 = 45 degrees)
            self.corrupted       = False
            self.level: List[BuildSector.SectLevel] = list()
            
            for lvl in self.bmap.Level:  ## TODO Refactor this, too
                self.slopeAbs[lvl.name] = 0.0
                self.slopeVector[lvl.name]  = Vector((0.0, 0.0))
            if self.data.floorstat & 2 != 0:
                self.slopeAbs[self.bmap.Level.FLOOR.name] = float(self.data.floorheinum) / 4096
            if self.data.ceilingstat & 2 != 0:
                self.slopeAbs[self.bmap.Level.CEILING.name] = float(self.data.ceilingheinum) / 4096
            
            for lvl in self.bmap.Level:
                self.level.append(self.SectLevel(self, lvl))
        
        def getPolyLines(self):
            polylines = list()
            for wallLoop in self.wallLoops:
                polyline = list()
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
                return "%sSector_%03d_Sky" % (prefix, self.sectorIndex)
            else:
                return "%sSector_%03d" % (prefix, self.sectorIndex)
        
        def getSpritesString(self):
            return " ".join([sprite.spriteIndex for sprite in self.sprites]).rstrip()
    
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
                        if sprite.data.lotag == 13:  ## C-9 Explosive Sprite
                            zC9Sprite = sprite.zScal
                            break
                if (zC9Sprite is not None) and (self.type == self.bmap.Level.FLOOR):
                    zScal = zC9Sprite
                return (self.sector.walls[0].xScal - xPos)*slopeX + (self.sector.walls[0].yScal - yPos)*slopeY + zScal
            
            def isParallaxing(self): ## mapster32: P toggle parallax
                return bool(self.cstat & 0x1)
            
            def isTrorOmit(self):  ## Experimental
                return (self.bmap.data.mapversion == 9) and bool(self.cstat & 0x400) and ((self.cstat & 0x80) == 0)
            
            def getName(self, sky=False, prefix=""):
                lvlName = "Floor" if self.type == self.bmap.Level.FLOOR else "Ceiling"
                if sky:
                    return "%sSector_%03d_%s_Sky" % (prefix, self.sector.sectorIndex, lvlName)
                else:
                    return "%sSector_%03d_%s" % (prefix, self.sector.sectorIndex, lvlName)
    
    class BuildWall:
        wallDataNames = namedtuple('SectorData', ['x', 'y', 'point2', 'nextwall', 'nextsector', 'cstat', 'picnum',
                                                  'overpicnum', 'shade', 'pal', 'xrepeat', 'yrepeat', 'xpanning',
                                                  'ypanning', 'lotag', 'hitag', 'extra'])
        wallDataFormat = '<ii6hb5Bhhh'
        def __init__(self, mapFile, parentBuildMap, indexInMap):
            raw = mapFile.read(struct.calcsize(self.wallDataFormat))
            self.data = self.wallDataNames._make(struct.unpack(self.wallDataFormat, raw))
            
            self.bmap           = parentBuildMap
            self.indexInMap     = indexInMap
            self.indexInSector  = None
            self.sector         = None
            self.xScal          = float(self.data.x) / 512
            self.yScal          = float(self.data.y) / 512
            self.neighborSectorIndex       = -1  ## This has in some cases shown more trustworthy results than relying on the walls nextwall and nextsector fields.
            self.neighborWallIndexInSector = -1  ## This has in some cases shown more trustworthy results than relying on the walls nextwall and nextsector fields.
            self.wallParts: List[BuildWall.WallPart] = list()
            
        def __post_init__(self):
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
                return "%sSector_%03d_MapWall_%03d" % (prefix, self.sector.sectorIndex, self.indexInMap)
            else:
                return "%sSector_%03d_SctWall_%03d" % (prefix, self.sector.sectorIndex, self.indexInSector)
        
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
                self.vertices     = list()
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
                nextWall = self.wall.getPoint2Wall()
                if nextWall is not None:
                    self.vertices.append(Vector(( self.wall.xScal, self.wall.yScal, self.sectBotLevel.getHeightAtPos(self.wall.xScal, self.wall.yScal) )))
                    self.vertices.append(Vector((  nextWall.xScal,  nextWall.yScal, self.sectBotLevel.getHeightAtPos( nextWall.xScal,  nextWall.yScal) )))
                    self.vertices.append(Vector((  nextWall.xScal,  nextWall.yScal, self.sectTopLevel.getHeightAtPos( nextWall.xScal,  nextWall.yScal) )))
                    self.vertices.append(Vector(( self.wall.xScal, self.wall.yScal, self.sectTopLevel.getHeightAtPos(self.wall.xScal, self.wall.yScal) )))
            
            def getClippedVertices(self):
                cverts = list()
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
            
            def getName(self, useIndexInMap=False, prefix=""):
                if self.wallType == self.bmap.WallType.REDBOT:
                    return self.wall.getName(useIndexInMap, prefix)+"_Bot"
                elif self.wallType == self.bmap.WallType.REDTOP:
                    return self.wall.getName(useIndexInMap, prefix)+"_Top"
                else:
                    return self.wall.getName(useIndexInMap, prefix)
    
    
    class BuildSprite:
        spriteDataNames = namedtuple('SectorData', ['x', 'y', 'z', 'cstat', 'picnum', 'shade', 'pal', 'clipdist', 'filler',
                                                    'xrepeat', 'yrepeat', 'xoffset', 'yoffset', 'sectnum', 'statnum', 'ang',
                                                    'owner', 'xvel', 'yvel', 'zvel', 'lotag', 'hitag', 'extra'])
        spriteDataFormat = '<iiihhb5Bbb10h'
        def __init__(self, mapFile, parentBuildMap, index):
            raw = mapFile.read(struct.calcsize(self.spriteDataFormat))
            self.data = self.spriteDataNames._make(struct.unpack(self.spriteDataFormat, raw))
            
            self.bmap        = parentBuildMap
            self.spriteIndex = index
            self.xScal       = float(self.data.x) / 512
            self.yScal       = float(self.data.y) / 512
            self.zScal       = float(self.data.z) / 8192
            self.angle       = BuildMap.calculateAngle(self.data.ang)
            if 0 <= self.data.sectnum < self.bmap.data.numsectors:
                self.bmap.sectors[self.data.sectnum].sprites.append(self)
            else:
                log.warning("Sprite %s sectnum is not in range of maps number of sectors: %s" % (self.spriteIndex, self.bmap.data.numsectors))
        
        def isFlippedX(self):
            ## cstat bit 2: 1 = x-flipped, 0 = normal
            return self.data.cstat&4 != 0
        
        def isFlippedY(self):
            ## cstat bit 3: 1 = y-flipped, 0 = normal
            return self.data.cstat&8 != 0
        
        def isFaceSprite(self):
            ## cstat bits 5-4: 00 = FACE sprite (default)
            return ((self.data.cstat>>4)&3) == 0
        
        def isWallSprite(self):
            ## cstat bits 5-4: 01 = WALL sprite (like masked walls)
            return ((self.data.cstat>>4)&3) == 1
        
        def isFloorSprite(self):
            ## cstat bits 5-4: 10 = FLOOR sprite (parallel to ceilings&floors)
            return ((self.data.cstat>>4)&3) == 2
        
        def isRealCentered(self):
            ## cstat bit 7: 1 = Real centered centering, 0 = foot center
            return self.data.cstat&128 != 0
        
        def getDataKey(self):
            ## This must return a key that is individual for every aspect of a Sprite
            ## that makes it neccessary to have a separate Datablock.
            ## So that when used for a dictionary we can reuse existing datablocks when they make no difference to the sprite.
            return (self.data.picnum, self.isFlippedX(), self.isFlippedY(), self.isFloorSprite(), self.isRealCentered())
        
        def isEffectSprite(self):
            ## https://wiki.eduke32.com/wiki/Special_Tile_Reference_Guide
            ## https://wiki.eduke32.com/wiki/Sector_effectors
            ## https://wiki.eduke32.com/wiki/Tilenum
            ## https://wiki.eduke32.com/wiki/Actor
            return (self.data.picnum >= 1) and (self.data.picnum <= 10)
        
        def isGunAmmo(self):
            return self.data.picnum in [21, 22, 23, 24, 25, 26, 27, 28, 29, 32, 37, 40, 41, 42, 44, 45, 46, 47, 49]
        
        def isHealthEquipment(self):
            return self.data.picnum in [51, 52, 53, 54, 55, 56, 57, 59, 60, 61, 100]
        
        def getScale(self, like_in_game=True):
            ## Return normalized Scale with 64 as 1
            if self.isFloorSprite():
                scale = ((self.data.yrepeat/64), (self.data.xrepeat/64), (self.data.xrepeat/64))
            else:
                scale = ((self.data.xrepeat/64), (self.data.xrepeat/64), (self.data.yrepeat/64))
            if like_in_game and (self.isGunAmmo() or self.isHealthEquipment()):
                if self.data.picnum == 26:  ## HEAVYHBOMB
                    return (0.125, 0.125, 0.125)
                elif self.data.picnum == 40:  ## AMMO
                    return (0.25, 0.25, 0.25)
                else:
                    return (0.5, 0.5, 0.5)
            else:
                return scale
        
        def getName(self, prefix=""):
            return "%sSprite_%03d" % (prefix, self.spriteIndex)

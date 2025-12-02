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

import bpy
import mathutils
from mathutils import Vector

log = logging.getLogger(__name__)



class BuildMapImporter:
    def __init__(self, buildMap, matManager, context, mapCollection, objectPrefix=""):
        self.bmap          = buildMap
        self.matManager    = matManager
        self.context       = context
        self.mapCollection = mapCollection
        self.objectPrefix  = objectPrefix
        self.wm            = self.context.window_manager
    
    def saveMapCustomProps(self, obj):
        if (self.bmap is not None) and (obj is not None):
            obj["mapversion"] = self.bmap.data.mapversion_major
            obj["posx"]       = self.bmap.data.posx
            obj["posy"]       = self.bmap.data.posy
            obj["posz"]       = self.bmap.data.posz
            obj["ang"]        = self.bmap.data.ang
            obj["cursectnum"] = self.bmap.data.cursectnum
            obj["numsectors"] = self.bmap.data.numsectors
            obj["numwalls"]   = self.bmap.data.numwalls
            obj["numsprites"] = self.bmap.data.numsprites
    
    def saveLevelCustomProps(self, level, obj):
        if (level is not None) and (obj is not None):
            obj["wallptr"]                 = level.sector.data.wallptr
            obj["wallnum"]                 = level.sector.data.wallnum
            obj["z"]                       = level.getZ()
            obj["cstat bit00 parallaxing"] = (level.cstat>>0)&1
            obj["cstat bit01 sloped"]      = (level.cstat>>1)&1
            obj["cstat bit02 swap-xy"]     = (level.cstat>>2)&1
            obj["cstat bit03 smoothness"]  = (level.cstat>>3)&1
            obj["cstat bit04 x-flip"]      = (level.cstat>>4)&1
            obj["cstat bit05 y-flip"]      = (level.cstat>>5)&1
            obj["cstat bit06 align"]       = (level.cstat>>6)&1
            obj["cstat bit07 masked"]      = (level.cstat>>7)&1
            obj["cstat bit08 trans"]       = (level.cstat>>8)&1
            obj["cstat bit09 TROR movblk"] = (level.cstat>>9)&1
            obj["cstat bit10 TROR"]        = (level.cstat>>10)&1
            obj["cstat bit11 TROR prjblk"] = (level.cstat>>11)&1
            obj["cstat bit12-15 reserved"] = "0b%s" % format(((level.cstat>>12)&15),'b').zfill(4)
            obj["picnum"]                  = level.getPicNum()
            obj["heinum"]                  = level.getHeiNum()
            obj["shade"]                   = level.getShade()
            obj["pal"]                     = level.getPal()
            obj["xpanning"]                = level.getXPanning()
            obj["ypanning"]                = level.getYPanning()
            obj["visibility"]              = level.sector.data.visibility
            obj["filler"]                  = level.sector.data.filler
            obj["lotag"]                   = level.sector.data.lotag
            obj["hitag"]                   = level.sector.data.hitag
            obj["extra"]                   = level.sector.data.extra
    
    def saveWallCustomProps(self, wall, obj):
        if (wall is not None) and (obj is not None):
            obj["x"]          = wall.data.x
            obj["y"]          = wall.data.y
            obj["point2"]     = wall.data.point2
            obj["nextwall"]   = wall.data.nextwall
            obj["nextsector"] = wall.data.nextsector
            obj["cstat bit00 blocking1"]         = (wall.data.cstat>>0)&1
            obj["cstat bit01 swap bot of invis"] = (wall.data.cstat>>1)&1
            obj["cstat bit02 align to bot"]      = (wall.data.cstat>>2)&1
            obj["cstat bit03 flip x"]            = (wall.data.cstat>>3)&1
            obj["cstat bit04 masking"]           = (wall.data.cstat>>4)&1
            obj["cstat bit05 1-way"]             = (wall.data.cstat>>5)&1
            obj["cstat bit06 blocking2"]         = (wall.data.cstat>>6)&1
            obj["cstat bit07 transluscence"]     = (wall.data.cstat>>7)&1
            obj["cstat bit08 flip y"]            = (wall.data.cstat>>8)&1
            obj["cstat bit09 transl. rev."]      = (wall.data.cstat>>9)&1
            obj["cstat bit10 yax upwall"]        = (wall.data.cstat>>10)&1
            obj["cstat bit11 yax downwall"]      = (wall.data.cstat>>11)&1
            obj["cstat bit12 rot 90deg"]         = (wall.data.cstat>>12)&1
            obj["cstat bit13-15 reserved"]       = "0b%s" % format(((wall.data.cstat>>13)&7),'b').zfill(3)
            obj["picnum"]     = wall.data.picnum
            obj["overpicnum"] = wall.data.overpicnum
            obj["shade"]      = wall.data.shade
            obj["pal"]        = wall.data.pal
            obj["xrepeat"]    = wall.data.xrepeat
            obj["yrepeat"]    = wall.data.yrepeat
            obj["xpanning"]   = wall.data.xpanning
            obj["ypanning"]   = wall.data.ypanning
            obj["lotag"]      = wall.data.lotag
            obj["hitag"]      = wall.data.hitag
            obj["extra"]      = wall.data.extra
    
    def saveSpriteCustomProps(self, sprite, obj):
        if (sprite is not None) and (obj is not None):
            obj["x"] = sprite.data.x
            obj["y"] = sprite.data.y
            obj["z"] = sprite.data.z
            obj["cstat bit00 blocking1"]          = (sprite.data.cstat>>0)&1
            obj["cstat bit01 transluscence"]      = (sprite.data.cstat>>1)&1
            obj["cstat bit02 flip x"]             = (sprite.data.cstat>>2)&1
            obj["cstat bit03 flip y"]             = (sprite.data.cstat>>3)&1
            obj["cstat bit05-04 face-wall-floor"] = "0b%s" % format(((sprite.data.cstat>>4)&3),'b').zfill(2)
            obj["cstat bit06 1-sided"]            = (sprite.data.cstat>>6)&1
            obj["cstat bit07 real center"]        = (sprite.data.cstat>>7)&1
            obj["cstat bit08 blocking2"]          = (sprite.data.cstat>>8)&1
            obj["cstat bit09 transl. rev."]       = (sprite.data.cstat>>9)&1
            obj["cstat bit10-14 reserved"]        = "0b%s" % format(((sprite.data.cstat>>10)&31),'b').zfill(5)
            obj["cstat bit15 invisible"]          = (sprite.data.cstat>>15)&1
            obj["picnum"] = sprite.data.picnum
            obj["shade"] = sprite.data.shade
            obj["pal"] = sprite.data.pal
            obj["clipdist"] = sprite.data.clipdist
            obj["filler"] = sprite.data.filler
            obj["xrepeat"] = sprite.data.xrepeat
            obj["yrepeat"] = sprite.data.yrepeat
            obj["xoffset"] = sprite.data.xoffset
            obj["yoffset"] = sprite.data.yoffset
            obj["sectnum"] = sprite.data.sectnum
            obj["statnum"] = sprite.data.statnum
            obj["ang"] = sprite.data.ang
            obj["owner"] = sprite.data.owner
            obj["xvel"] = sprite.data.xvel
            obj["yvel"] = sprite.data.yvel
            obj["zvel"] = sprite.data.zvel
            obj["lotag"] = sprite.data.lotag
            obj["hitag"] = sprite.data.hitag
            obj["extra"] = sprite.data.extra

    def getEdgesFromPolylines(self, polylines):
        edges = list()
        for polyline in polylines:
            for i in range(len(polyline)):
                edges.append((polyline[i], polyline[(i + 1) % len(polyline)]))
        return edges
    
    def cutPolygonIntoTrapezoids(self, polylines):
        yCoords = sorted(set(vector.y for polyline in polylines for vector in polyline))
        trapezoids = list()
    
        for yIdx in range(len(yCoords)-1):
            xCoords = list()
            for edge in self.getEdgesFromPolylines(polylines):
                v0, v1 = edge if edge[0].y <= edge[1].y else (edge[1], edge[0])
                if not (v0.y >= yCoords[yIdx + 1] or v1.y <= yCoords[yIdx]):
                    x0 = v0.x if v0.y >= yCoords[yIdx]   else (yCoords[yIdx]   - v0.y) * (v1.x - v0.x) / (v1.y - v0.y) + v0.x
                    x1 = v1.x if v1.y <= yCoords[yIdx+1] else (yCoords[yIdx+1] - v0.y) * (v1.x - v0.x) / (v1.y - v0.y) + v0.x
                    xCoords.append((x0, x1))
            
            xCoords.sort(key=lambda x: x[0] + x[1])

            xIdx = 0
            while xIdx < len(xCoords):
                xEndIdx = xIdx + 1
                while (xEndIdx+2 < len(xCoords)) \
                        and (xCoords[xEndIdx+1][0] <= xCoords[xEndIdx][0]) \
                        and (xCoords[xEndIdx+1][1] <= xCoords[xEndIdx][1]):
                    xEndIdx += 2
                trapezoids.append([ Vector(( xCoords[xIdx][0],    yCoords[yIdx]   )),
                                    Vector(( xCoords[xEndIdx][0], yCoords[yIdx]   )),
                                    Vector(( xCoords[xEndIdx][1], yCoords[yIdx+1] )),
                                    Vector(( xCoords[xIdx][1],    yCoords[yIdx+1] )) ])
                xIdx = xEndIdx + 1
        
        return trapezoids
    
    
    
    def addSpawn(self):
        verts = [
            Vector(( 0.334, 0, 0)),
            Vector((-0.334, 0, 0)),
            Vector((0,  0.334, 0)),
            Vector((0, -0.334, 0))
        ]
        edges = [(0, 1), (0, 2), (0, 3)]
        mesh = bpy.data.meshes.new("%sSpawn"%self.objectPrefix)
        obj = bpy.data.objects.new(mesh.name, mesh)
        self.mapCollection.objects.link(obj)
        mesh.from_pydata(verts, edges, [])
        obj.location.x += self.bmap.posxScal
        obj.location.y += self.bmap.posyScal * -1
        obj.location.z += self.bmap.poszScal * -1
        obj.rotation_euler.z += self.bmap.spawnAngle
        self.saveMapCustomProps(obj)
    
    
    def addSprites(self, wallSpriteOffset, scaleSpritesLikeInGame=True, shadeToVertexColors=True):
        log.debug(f"Adding Sprites")
        spriteCollection = bpy.data.collections.new(f"{self.objectPrefix}Sprites")
        self.mapCollection.children.link(spriteCollection)
        colFaceSprites = bpy.data.collections.new(f"{self.objectPrefix}FaceSprites")
        colWallSprites = bpy.data.collections.new(f"{self.objectPrefix}WallSprites")
        colFloorSprites = bpy.data.collections.new(f"{self.objectPrefix}FloorSprites")
        colEffectSprites = bpy.data.collections.new(f"{self.objectPrefix}EffectSprites")
        colItemSprites = bpy.data.collections.new(f"{self.objectPrefix}Items")
        colWeaponSprites = bpy.data.collections.new(f"{self.objectPrefix}Weapons")
        colAmmoSprites = bpy.data.collections.new(f"{self.objectPrefix}Ammo")
        colEnemySprites = bpy.data.collections.new(f"{self.objectPrefix}Enemies")
        colNoTextureSprites = bpy.data.collections.new(f"{self.objectPrefix}NoTexture")
        colNoTextureSprites.color_tag = 'COLOR_01'  # Red
        spriteCollection.children.link(colFaceSprites)
        spriteCollection.children.link(colWallSprites)
        spriteCollection.children.link(colFloorSprites)
        spriteCollection.children.link(colEffectSprites)
        spriteCollection.children.link(colItemSprites)
        spriteCollection.children.link(colWeaponSprites)
        spriteCollection.children.link(colAmmoSprites)
        spriteCollection.children.link(colEnemySprites)
        spriteCollection.children.link(colNoTextureSprites)
        spriteCache = dict()
        
        total_sprites = max(1, self.bmap.data.numsprites)
        step_sprites  = max(1, total_sprites // 100)
        for sprite in self.bmap.sprites:
            if (sprite.spriteIndex % step_sprites) == 0:
                self.wm.progress_update(sprite.spriteIndex / total_sprites)
            
            if sprite.isEnemy():
                collection = colEnemySprites
            elif sprite.isWeapon():
                collection = colWeaponSprites
            elif sprite.isAmmo():
                collection = colAmmoSprites
            elif sprite.isHealthEquipment():
                collection = colItemSprites
            elif sprite.isEffectSprite():
                collection = colEffectSprites
            elif sprite.isFaceSprite():
                collection = colFaceSprites
            elif sprite.isWallSprite():
                collection = colWallSprites
            elif sprite.isFloorSprite():
                collection = colFloorSprites
            else:
                collection = spriteCollection
            
            spriteWithEqualData = spriteCache.get(sprite.getDataKey(), None)
            if spriteWithEqualData is None:
                objCrtr = self.meshObjectCreator(self.matManager, name=sprite.getName(prefix=self.objectPrefix), shadeToVertexColors=shadeToVertexColors)
                dims = self.matManager.getDimensions(sprite.data.picnum)
                scale_x = dims[0] / 64.0
                scale_y = dims[1] / 64.0
                flip_x = sprite.isFlippedX()
                flip_y = sprite.isFlippedY()
                coff_x = 0.0 # - (scale_x % 2) / 64
                coff_y = 0.0 # - (scale_y % 2) / 64
                picnum_entry = self.matManager.getPicnumEntry(sprite.data.picnum)
                if ((picnum_entry is not None) and picnum_entry.art_picanm_available and (picnum_entry.center_offset_x is not None) and (picnum_entry.center_offset_y is not None)):
                    coff_x -= picnum_entry.center_offset_x / 32 * (-1.0 if flip_x else 1.0)
                    coff_y += picnum_entry.center_offset_y / 32 * (-1.0 if flip_y else 1.0)
                
                if sprite.isFloorSprite():
                    objCrtr.verts = [Vector((-1 * scale_y + coff_y, -1 * scale_x + coff_x, 0)),
                                     Vector(( 1 * scale_y + coff_y, -1 * scale_x + coff_x, 0)),
                                     Vector(( 1 * scale_y + coff_y,  1 * scale_x + coff_x, 0)),
                                     Vector((-1 * scale_y + coff_y,  1 * scale_x + coff_x, 0))]
                elif sprite.isRealCentered():
                    objCrtr.verts = [Vector((0,  1 * scale_x + coff_x, -1 * scale_y + coff_y)),
                                     Vector((0,  1 * scale_x + coff_x,  1 * scale_y + coff_y)),
                                     Vector((0, -1 * scale_x + coff_x,  1 * scale_y + coff_y)),
                                     Vector((0, -1 * scale_x + coff_x, -1 * scale_y + coff_y))]
                else:
                    objCrtr.verts = [Vector((0,  1 * scale_x + coff_x, 0 * scale_y + coff_y)),
                                     Vector((0,  1 * scale_x + coff_x, 2 * scale_y + coff_y)),
                                     Vector((0, -1 * scale_x + coff_x, 2 * scale_y + coff_y)),
                                     Vector((0, -1 * scale_x + coff_x, 0 * scale_y + coff_y))]
                
                ifx = int(flip_x)
                ify = int(flip_y)
                objCrtr.addFace([0, 1, 2, 3], sprite.data.picnum, sprite.getShadeColor())
                objCrtr.vertUVs = [(1-ifx, ify), (1-ifx, 1-ify), (ifx, 1-ify), (ifx, ify)]
                newObj = objCrtr.create(collection)
                spriteCache[sprite.getDataKey()] = newObj
            else:
                ## Create a new Object linked to existing data
                newObj = bpy.data.objects.new(sprite.getName(prefix=self.objectPrefix), spriteWithEqualData.data)
                collection.objects.link(newObj)
            
            newObj.scale = sprite.getScale(scaleSpritesLikeInGame)
            newObj.location.x += sprite.xScal
            newObj.location.y += sprite.yScal * -1
            newObj.location.z += sprite.zScal * -1
            newObj.rotation_euler.z += sprite.angle
            
            if sprite.isWallSprite():
                ## In case of Wall Sprites, give them a customisable offset to the wall to avoid z-fighting
                xoffset = wallSpriteOffset * math.cos(sprite.angle)
                yoffset = wallSpriteOffset * math.sin(sprite.angle)
                newObj.location.x += xoffset
                newObj.location.y += yoffset
            
            if not self.matManager.hasTexture(sprite.data.picnum):
                colNoTextureSprites.objects.link(newObj)
            
            self.saveSpriteCustomProps(sprite, newObj)
        
        ## Delete NoTexture Collection if it contains nothing
        if len(colNoTextureSprites.objects) == 0:
            spriteCollection.children.unlink(colNoTextureSprites)
            bpy.data.collections.remove(colNoTextureSprites)
    
    
    
    def calculateSectorUVCoords(self, level, xCoord, yCoord):
        picDimX,picDimY = self.matManager.getDimensions(level.getPicNum())
        panX,panY       = level.getTexPanning()
        expFactor       = level.getTexExpansion()
        uvXFactor       = float(32)/picDimX * expFactor
        uvYFactor       = float(32)/picDimY * expFactor
        flipXFactor     = level.getTexFlipXFactor()
        flipYFactor     = level.getTexFlipYFactor()
        
        if level.isTexAlignToFirstWall():
            ## convert xCoord and yCoord to a coordinate system centered on and aligned with the first sector wall
            vertexVectorAligned = Vector((xCoord, yCoord*-1)) - level.sector.walls[0].startVect
            vertexVectorAligned.rotate(mathutils.Matrix.Rotation(level.sector.walls[0].angle, 2))
            
            ## Correct Y Dimension for Alligned Case
            zDiff = level.zScal*-1 - level.getHeightAtPos(xCoord, yCoord)*-1
            vertexVectorAligned_y = float(math.sqrt(zDiff * zDiff + vertexVectorAligned.y * vertexVectorAligned.y))
            if vertexVectorAligned.y < 0:
                vertexVectorAligned_y *= -1  ## Restore Sign
            
            if level.getTexSwapXY():
                uvx = vertexVectorAligned_y*flipXFactor*uvXFactor+panX
                uvy = vertexVectorAligned.x*flipYFactor*uvYFactor+panY
            else:
                uvx = vertexVectorAligned.x*flipXFactor*uvXFactor+panX
                uvy = vertexVectorAligned_y*flipYFactor*uvYFactor+panY
        else:
            if level.getTexSwapXY():
                uvx = yCoord*flipXFactor*uvXFactor+panX
                uvy = xCoord*flipYFactor*uvYFactor+panY
            else:
                uvx = xCoord*flipXFactor*uvXFactor+panX
                uvy = yCoord*flipYFactor*uvYFactor+panY
        return (uvx,uvy)
    
    
    def calculateWallUVCoord(self, inputCoord, alignTexZ, flipFactor, repeat, panning, picDim, panDivisor, panSign, pixFactor, flipPlus, flipAtStart):
        outputUV = inputCoord - alignTexZ     ## Align to alignTexZPx (Both must already be relative to the Bottom of the wall)
        
        if flipAtStart and flipFactor < 0:
            outputUV *= flipFactor
            outputUV += flipPlus              ## + one wall width to make it appear as the wall mirrored on itself instead mirrored on the origin
        
        outputUV *= repeat * 8 * pixFactor    ## repeat * 8 tells how many pixels the whole width of the wall covers. After this line outputUV means: "Pixels covered by wallWidth"
        outputUV /= float(picDim)             ## convert pixel coordinates into image coordinates from here on
        outputUV += (float(panning) / float(panDivisor)) * panSign
        
        if not flipAtStart and flipFactor < 0:
            outputUV *= flipFactor
            outputUV += flipPlus              ## + one wall width to make it appear as the wall mirrored on itself instead mirrored on the origin
        
        return outputUV
    
    
    def calculateWallUVCoords(self, wPart, vertex):
        wall = wPart.wall
        alignTexZ = wPart.alignTexZ * -1
        picDimX, picDimY = self.matManager.getDimensions(wPart.getPicNum())
        
        # if the 90°-rotation flag is set, swap texture width and height
        if wall.getTexRotate():
            picDimX, picDimY = picDimY, picDimX
        
        # compute normalized distance along the wall (0 to 1)
        vertexDistFromWallStart = (Vector((vertex.x, vertex.y*-1)) - wall.startVect).length
        relativeWallPos = 0.0 if wall.length == 0 else (vertexDistFromWallStart / wall.length)
        
        # compute vertical position relative to floor
        zCoordRelativeToZBottom = (vertex.z * -1) - (wPart.zBottom * -1)
        alignTexZRelativeToZBottom = alignTexZ - (wPart.zBottom * -1)
        
        ## X panning increases when the texture is moved left (uv coordinate moved right) and is realative to the texture width (not a fixed value like Y Panning)
        uvx = self.calculateWallUVCoord(
            inputCoord  = relativeWallPos,
            alignTexZ   = 0,
            flipFactor  = wall.getTexFlipXFactor(),
            repeat      = wall.data.xrepeat,
            panning     = wall.data.xpanning,
            picDim      = picDimX,
            panDivisor  = picDimX,
            panSign     = 1,
            pixFactor   = 1,
            flipPlus    = 1,
            flipAtStart = True
        )
        
        ## 1pud = 1024z = 4px = 0.125m
        ## default wall height = 16pud = 16384z = 64px = 2m
        ## the default wall height of 8192*2 z units is supposed to fit 64 pixels of a non stretched texture
        ## (wall.yrepeat * 8) this is how many pixels a wall of the default height of (8192*2) really covers! (not 64 anymore) (a wall of different height covers different amout of pixels)
        ## ypanning=256 means moving the texture up (vertex down) one size of the whole image how it appears stretched (moving much more if stretched wide)
        uvy = self.calculateWallUVCoord(
            inputCoord  = zCoordRelativeToZBottom,
            alignTexZ   = alignTexZRelativeToZBottom,
            flipFactor  = wall.getTexFlipYFactor(),
            repeat      = wall.data.yrepeat,
            panning     = wall.data.ypanning,
            picDim      = picDimY,
            panDivisor  = 256,
            panSign     = -1,
            pixFactor   = 0.5,
            flipPlus    = 0,
            flipAtStart = False
        )
        
        # if rotated, rotate UV by 90° clockwise:
        if wall.getTexRotate():
            return (uvy, 1.0 - uvx)
        
        return (uvx, uvy)
    
    
    
    def addMapGeometry(self, splitSectors, splitWalls, splitSky, shadeToVertexColors=True):
        log.debug(f"Adding Map Geometry")
        collectionMapGeo = bpy.data.collections.new("%sMap"%self.objectPrefix)
        self.mapCollection.children.link(collectionMapGeo)
        if splitWalls:
            collectionWalls = bpy.data.collections.new("%sWalls"%self.objectPrefix)
            self.mapCollection.children.link(collectionWalls)
        if splitSky:
            collectionSkyGeo = bpy.data.collections.new("%sSky"%self.objectPrefix)
            self.mapCollection.children.link(collectionSkyGeo)
        
        objCrtrMap = self.meshObjectCreator(self.matManager, name="%sMapGeometry"%self.objectPrefix, shadeToVertexColors=shadeToVertexColors)
        objCrtrSky = self.meshObjectCreator(self.matManager, name="%sMapGeometry_Sky"%self.objectPrefix, shadeToVertexColors=shadeToVertexColors)
        
        total_sectors = max(1, self.bmap.data.numsectors)
        step_sectors  = max(1, total_sectors // 100)
        for sector in self.bmap.getSectors():
            if (sector.sectorIndex % step_sectors) == 0:
                self.wm.progress_update(sector.sectorIndex / total_sectors)
            
            ## Try to get polygon partitions from blenders tessellate_polygon method
            ## This can fail on degenerate geometry
            faceIndices = mathutils.geometry.tessellate_polygon(sector.getPolyLines())
            faceIndicesCovered = set([idx  for face in faceIndices  for idx in face])
            tessellationValid = len(faceIndicesCovered) == sector.data.wallnum
            if not tessellationValid:
                log.warning("tessellate_polygon result invalid for sector %s likely because of degenerate geometry! Using Fallback." % sector.sectorIndex)
                log.debug("tessellate_polygon result invalid for sector %s: sector.data.wallnum %s  !=  len(faceIndicesCovered) %s  faceIndicesCovered: %s" % (sector.sectorIndex, sector.data.wallnum, len(faceIndicesCovered), faceIndicesCovered))

            for level in sector.getLevel():
                levelSplitSky = splitSky and level.isParallaxing()
                if splitSectors:
                    objCrtrLvl = self.meshObjectCreator(self.matManager, name=level.getName(sky=levelSplitSky, prefix=self.objectPrefix), shadeToVertexColors=shadeToVertexColors)
                else:
                    objCrtrLvl = objCrtrSky if levelSplitSky else objCrtrMap
                
                if tessellationValid:
                    for faceIdxTriple in faceIndices:
                        objCrtrLvl.addFace([objCrtrLvl.vertIdx+faceIdxTriple[0], objCrtrLvl.vertIdx+faceIdxTriple[1], objCrtrLvl.vertIdx+faceIdxTriple[2]], level.getPicNum(), level.getShadeColor(), flipped=level.isCeiling())
                        for faceIdx in faceIdxTriple:
                            objCrtrLvl.vertUVs.append(self.calculateSectorUVCoords(level, sector.walls[faceIdx].xScal, sector.walls[faceIdx].yScal))
                    for wall in sector.walls:
                        objCrtrLvl.verts.append(Vector((wall.xScal, wall.yScal*-1, level.getHeightAtPos(wall.xScal, wall.yScal)*-1)))
                        objCrtrLvl.vertIdx += 1
                else:
                    ## Fallback in case tessellate_polygon did not succeed - likely because of degenerate geometry
                    for trapezoid in self.cutPolygonIntoTrapezoids(sector.getPolyLines()):
                        face = list()
                        for vert in trapezoid:
                            z = level.getHeightAtPos(vert.x, vert.y)
                            objCrtrLvl.verts.append(Vector((vert.x, vert.y*-1, z*-1)))
                            objCrtrLvl.vertUVs.append(self.calculateSectorUVCoords(level, vert.x, vert.y))
                            face.append(objCrtrLvl.vertIdx)
                            objCrtrLvl.vertIdx += 1
                        objCrtrLvl.addFace(face, level.getPicNum(), level.getShadeColor(), flipped=level.isFloor())
                
                if splitSectors:
                    objCrtrLvl.create(collectionSkyGeo if levelSplitSky else collectionMapGeo)
                    self.saveLevelCustomProps(level, objCrtrLvl.obj)

            for wall in sector.walls:
                objCrtrWall = objCrtrMap
                for wPart in wall.getWallParts():
                    splitToSky = splitSky and wPart.isSky()
                    splitThisWall = splitWalls or splitToSky
                    if splitThisWall:
                        objCrtrWall = self.meshObjectCreator(self.matManager, name=wPart.getName(prefix=self.objectPrefix), shadeToVertexColors=shadeToVertexColors)
                    face = list()
                    for vert in wPart.getClippedVertices():
                        objCrtrWall.verts.append(Vector((vert.x, vert.y*-1, vert.z*-1)))
                        objCrtrWall.vertUVs.append(self.calculateWallUVCoords(wPart, vert))
                        face.append(objCrtrWall.vertIdx)
                        objCrtrWall.vertIdx += 1
                    if len(face) > 0:
                        objCrtrWall.addFace(face, wPart.getPicNum(), wPart.getShadeColor())
                    if splitThisWall:
                        objCrtrWall.create(collectionSkyGeo if splitToSky else collectionWalls)
                        self.saveWallCustomProps(wall, objCrtrWall.obj)
        
        objCrtrMap.create(collectionMapGeo)
        if splitSky:
            objCrtrSky.create(collectionSkyGeo)

    class meshObjectCreator:
        def __init__(self, matManager, name="NewObject", shadeToVertexColors=True):
            self.matManager = matManager
            self.name = name
            self.verts = list()
            self.vertUVs = list()
            self.edges = list()
            self.faces = list()
            self.facePicnums = list()
            self.faceShadeColors = list()
            self.faceIsFlipped = list()
            self.picnumMatIdxDict = dict()
            self.obj = None
            self.vertColorLayer = None
            self.shadeToVertexColors = shadeToVertexColors
            self.vertIdx = 0
        
        def addFace(self, face, picnum=0, vertShadeColor=(1.0, 1.0, 1.0, 1.0), flipped=False):
            self.faces.append(face)
            self.facePicnums.append(picnum)
            self.faceShadeColors.append(vertShadeColor)
            self.faceIsFlipped.append(flipped)
        
        def create(self, collection=None):
            if len(self.verts) <= 0:
                return self.obj

            mesh = bpy.data.meshes.new(self.name)
            mesh.from_pydata(self.verts, self.edges, self.faces)
            # mesh.validate(verbose=True)  # useful for development when the mesh may be invalid.
            self.obj = bpy.data.objects.new(self.name, mesh)

            if collection is not None:
                collection.objects.link(self.obj)

            ## Create the materials and append them to the new object
            for matIdx, picnum in enumerate(set(self.facePicnums)):
                mat = self.matManager.getMaterial(picnum)
                self.obj.data.materials.append(mat)
                self.picnumMatIdxDict[picnum] = matIdx

            ## Create UV Map
            newUVMap = self.obj.data.uv_layers.new(name="UVMap", do_init=False)
            for idx, loop in enumerate(self.obj.data.loops):
                newUVMap.data[idx].uv = self.vertUVs[idx]

            ## Loop over the faces again to assign the materials, vertex colors and flip normals for correct face orientation
            if self.shadeToVertexColors:
                self.vertColorLayer = self.obj.data.vertex_colors.new(name="Shade", do_init=False)
                #self.vertColorLayer = self.obj.data.color_attributes.new(name="Shade", domain='CORNER', type='BYTE_COLOR')  ## This method results in lighter colors (gamma correction?)! e.g.: 0xd6d0d2 instead of 0xaba1a5
            for face in self.obj.data.polygons:
                face.material_index = self.picnumMatIdxDict[self.facePicnums[face.index]]
                if self.faceIsFlipped[face.index]:
                    face.flip()
                if self.vertColorLayer is not None:
                    for loop_idx in face.loop_indices:
                        self.vertColorLayer.data[loop_idx].color = self.faceShadeColors[face.index]

            return self.obj

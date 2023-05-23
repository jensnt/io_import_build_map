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
import os
import re

import bpy

log = logging.getLogger(__name__)



class materialManager:
    def __init__(self, texFolder, userArtTexFolder, reuseExistingMaterials=True, sampleClosestTexel=True, proceduralMaterialEffects=False, useBackfaceCulling=False):
        log.debug("materialManager init with texFolder: %s  userArtTexFolder: %s  sampleClosestTexel: %s" % (texFolder, userArtTexFolder, sampleClosestTexel))
        self.textureFolder = None
        self.userArtTextureFolder = None
        self.texFileMap = None
        self.userArtTexFileMap = None
        self.materialDict = dict()
        self.dimensionsDict = dict()
        self.picnumUserArtStart = 3584
        self.existingMats = dict()
        self.reuseExistingMaterials = reuseExistingMaterials
        self.sampleClosestTexel = sampleClosestTexel
        self.proceduralMaterialEffects = proceduralMaterialEffects
        self.useBackfaceCulling = useBackfaceCulling
        
        for existingMat in bpy.data.materials:
            self.existingMats[existingMat.name] = existingMat
        
        if (texFolder is not None) and (os.path.exists(texFolder)):
            self.textureFolder = texFolder
            self.texFileMap = self.getFileMap(self.textureFolder)
        if (userArtTexFolder is not None) and (os.path.exists(userArtTexFolder)):
            self.userArtTextureFolder = userArtTexFolder
            self.userArtTexFileMap = self.getFileMap(self.userArtTextureFolder)
    
    def getFileMap(self, path):
        filemap = dict()
        if (path is not None) and (os.path.exists(path)):
            for root, dirs, files in os.walk(path):
                for filename in files:
                    if filename.endswith(".png"):
                        filemap[filename] = os.path.join(root, filename)
        return filemap

    def getArtFileNumber(self, picnum):
        return int(picnum / 256)
    
    def getArtFileIndex(self, picnum):
        return int(picnum % 256)
    
    def getTextureFileName(self, picnum):
        return "%03d-%03d.png" % (self.getArtFileIndex(picnum), self.getArtFileNumber(picnum))
    
    def getMaterialName(self, picnum):
        return "picnum%04d_%03d-%03d" % (picnum, self.getArtFileIndex(picnum), self.getArtFileNumber(picnum))
    
    def findPicnumFile(self, picnum, texFileMap, userArtTexFileMap=None):
        imgFilePath = None
        imgFileNameExpected = self.getTextureFileName(picnum)
        
        ## First search for User Art if in User Art range and available
        if (picnum >= self.picnumUserArtStart) and isinstance(userArtTexFileMap, dict) and (len(userArtTexFileMap) > 0):
            ## Try to get User Art file with completely defined filename
            imgFilePath = userArtTexFileMap.get(imgFileNameExpected)
            ## If none was found using completely defined filename, try with RegEx
            if imgFilePath is None:
                regex = re.compile(r"^%03d-.{3}\.png$" % self.getArtFileIndex(picnum))
                for imgFileName in userArtTexFileMap.keys():
                    if regex.match(imgFileName):
                        imgFilePath = userArtTexFileMap.get(imgFileName)
                        break
                log.debug("Tried to find User Art using RegEx, resulting in: %s" % imgFilePath)
        
        ## If we could not get any User Art file, search the normal file map
        if (imgFilePath is None) and isinstance(texFileMap, dict) and (len(texFileMap) > 0):
            imgFilePath = texFileMap.get(imgFileNameExpected)
        
        ## If we could still not get any image file, search the User Art file map again in the full picnum range
        ## Normally the User Art folder should only contain textures in the range: picnum >= 3584
        ## But the user might have put textures outside that range there anyway...
        if (imgFilePath is None) and isinstance(userArtTexFileMap, dict) and (len(userArtTexFileMap) > 0):
            imgFilePath = userArtTexFileMap.get(imgFileNameExpected)
            if imgFilePath is not None:
                log.debug("Non User Art texture found in User Art folder: %s" % imgFilePath)
        
        return imgFilePath
    
    def __createMaterial(self, picnum):
        matName = self.getMaterialName(picnum)
        existingMat = self.existingMats.get(matName, None)
        imgFilePath = self.findPicnumFile(picnum, self.texFileMap, self.userArtTexFileMap)
        defaultImgName = self.getTextureFileName(picnum)
        
        ## Try reusing an existing material
        if self.reuseExistingMaterials and (existingMat is not None):
            ## Try to find the image node in the existing material
            imageSearchName = defaultImgName if imgFilePath is None else os.path.basename(imgFilePath)

            for node in existingMat.node_tree.nodes:
                if (node.type == 'TEX_IMAGE') \
                        and (node.name == 'Image Texture') \
                        and (node.image is not None) \
                        and (node.image.name == imageSearchName):
                    self.dimensionsDict[picnum] = node.image.size
                    break
            else:
                log.debug("Found existing material but no image node!: %s  %s" % (matName, imageSearchName))
                if imgFilePath is not None:
                    ## In case no image node is found but we know the path of the texture,
                    ## just generate one to get the size from it. It can be deleted again afterwards.
                    nodeImg = existingMat.node_tree.nodes.new(type='ShaderNodeTexImage')
                    nodeImg.location = (-300, 625)
                    nodeImg.interpolation = 'Closest' if self.sampleClosestTexel else 'Smart'

                    nodeImg.image = bpy.data.images.load(imgFilePath)
                    self.dimensionsDict[picnum] = nodeImg.image.size
                    existingMat.node_tree.nodes.remove(nodeImg)  ## Delete the Node again
            self.materialDict[picnum] = existingMat
            return existingMat
                
        
        ## Create new material
        newMat = bpy.data.materials.new(name=matName)
        newMat.use_nodes = True
        newMat.blend_method = 'CLIP'
        newMat.use_backface_culling = self.useBackfaceCulling
        
        ## Remove all nodes in the materials node tree
        for node in newMat.node_tree.nodes:
            newMat.node_tree.nodes.remove(node)

        ## Create and connect basic nodes
        nodePbr = newMat.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
        nodePbr.location = (0, 325)
        nodeMatOut = newMat.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
        nodeMatOut.location = (300, 325)
        newMat.node_tree.links.new(nodePbr.outputs["BSDF"], nodeMatOut.inputs["Surface"])
        
        nodeImg = newMat.node_tree.nodes.new(type='ShaderNodeTexImage')
        nodeImg.location = (-400, 325)
        nodeImg.interpolation = 'Closest' if self.sampleClosestTexel else 'Smart'
        newMat.node_tree.links.new(nodeImg.outputs["Color"], nodePbr.inputs["Base Color"])
        newMat.node_tree.links.new(nodeImg.outputs["Alpha"], nodePbr.inputs["Alpha"])
        
        ## Adding nodes to created materials to achieve a more realistic appearance.
        if self.proceduralMaterialEffects:
            nodeBevel = newMat.node_tree.nodes.new(type='ShaderNodeBevel')
            nodeBevel.samples = 16
            nodeBevel.inputs["Radius"].default_value = 0.03
            
            nodeBump1 = newMat.node_tree.nodes.new(type='ShaderNodeBump')
            nodeBump1.inputs["Strength"].default_value = 0.08
            
            nodeBump2 = newMat.node_tree.nodes.new(type='ShaderNodeBump')
            nodeBump2.inputs["Strength"].default_value = 0.1
            
            nodeMusgrave = newMat.node_tree.nodes.new(type='ShaderNodeTexMusgrave')
            nodeMusgrave.inputs["Scale"].default_value = 0.5
            nodeMusgrave.inputs["Detail"].default_value = 15
            nodeMusgrave.inputs["Dimension"].default_value = 1
            nodeMusgrave.inputs["Lacunarity"].default_value = 3
            
            nodeTexCoord = newMat.node_tree.nodes.new(type='ShaderNodeTexCoord')
            
            nodeAO = newMat.node_tree.nodes.new(type='ShaderNodeAmbientOcclusion')
            nodeAO.inputs["Distance"].default_value = 0.8
            nodeMix = newMat.node_tree.nodes.new(type='ShaderNodeMixRGB')
            nodeMix.blend_type = 'MULTIPLY'
            nodeMix.inputs["Fac"].default_value = 0.8
            
            nodeImg.location = (-900, 325)
            nodeBevel.location = (-200, -300)
            nodeBump1.location = (-400, -300)
            nodeBump2.location = (-600, -100)
            nodeMusgrave.location = (-600, -300)
            nodeTexCoord.location = (-800, -300)
            nodeAO.location = (-800, 625)
            nodeMix.location = (-400, 625)
            
            newMat.node_tree.links.new(nodeBevel.outputs["Normal"], nodePbr.inputs["Normal"])
            newMat.node_tree.links.new(nodeBump1.outputs["Normal"], nodeBevel.inputs["Normal"])
            newMat.node_tree.links.new(nodeMusgrave.outputs["Fac"], nodeBump1.inputs["Height"])
            newMat.node_tree.links.new(nodeBump2.outputs["Normal"], nodeBump1.inputs["Normal"])
            newMat.node_tree.links.new(nodeImg.outputs["Color"], nodeBump2.inputs["Height"])
            newMat.node_tree.links.new(nodeTexCoord.outputs["Object"], nodeMusgrave.inputs["Vector"])
            
            newMat.node_tree.links.new(nodeAO.outputs["Color"], nodeMix.inputs["Color2"])
            newMat.node_tree.links.new(nodeImg.outputs["Color"], nodeMix.inputs["Color1"])
            newMat.node_tree.links.new(nodeMix.outputs["Color"], nodePbr.inputs["Base Color"])
        
        if imgFilePath is not None:
            nodeImg.image = bpy.data.images.load(imgFilePath)
            self.dimensionsDict[picnum] = nodeImg.image.size
        else:
            # Create a new default image for this material since we don't have a texture file
            nodeImg.image = bpy.data.images.new(name=defaultImgName, width=32, height=32, alpha=True)
        
        self.materialDict[picnum] = newMat
        return newMat

    def getMaterial(self, picnum):
        return self.materialDict.get(picnum) or self.__createMaterial(picnum)
    
    def getDimensions(self, picnum):
        if picnum not in self.materialDict:
            self.__createMaterial(picnum)
            
        return self.dimensionsDict.get(picnum, (32, 32))

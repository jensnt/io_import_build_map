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
from typing import Optional, Tuple, Dict

import bpy

from .texture_importer import TextureImporter, PicnumEntry

log = logging.getLogger(__name__)



class materialManager:
    def __init__(self, bmap, picnum_dict, texFolder, userArtTexFolder, reuseExistingMaterials=True, sampleClosestTexel=True, shadeToVertexColors=True, proceduralMaterialEffects=False, useBackfaceCulling=False):
        log.debug("materialManager init with texFolder: %s  userArtTexFolder: %s  sampleClosestTexel: %s  shadeToVertexColors: %s" % (texFolder, userArtTexFolder, sampleClosestTexel, shadeToVertexColors))
        self.blversion = bpy.app.version
        self.picnum_dict = picnum_dict
        self.textureFolder = None
        self.userArtTextureFolder = None
        self.texFileMap: Dict[str, str] = {}
        self.userArtTexFileMap: Dict[str, str] = {}
        self.materialDict: Dict[int, Tuple[bpy.types.Material, Optional[PicnumEntry]]] = {}
        self.dimensionsDict = {}
        self.existingMats = {}
        self.reuseExistingMaterials = reuseExistingMaterials
        self.sampleClosestTexel = sampleClosestTexel
        self.shadeToVertexColors = shadeToVertexColors
        self.proceduralMaterialEffects = proceduralMaterialEffects
        self.useBackfaceCulling = useBackfaceCulling
        
        for existingMat in bpy.data.materials:
            if not existingMat.use_nodes or existingMat.node_tree is None:
                log.debug(f"Material '{existingMat.name}' does not use nodes. Not adding to existing materials List.")
                continue
            self.existingMats[existingMat.name] = existingMat
        
        if (texFolder is not None) and (os.path.exists(texFolder)):
            self.textureFolder = texFolder
            TextureImporter.fillFileMap(self.textureFolder, self.texFileMap)
        if (userArtTexFolder is not None) and (os.path.exists(userArtTexFolder)):
            self.userArtTextureFolder = userArtTexFolder
            TextureImporter.fillFileMap(self.userArtTextureFolder, self.userArtTexFileMap)
    
    def getTextureFileNameDefault(self, picnum):
        return "%04d.png" % picnum
    
    def getMaterialName(self, picnum):
        return "picnum%04d_%03d-%03d" % (picnum, TextureImporter.getArtFileIndex(picnum), TextureImporter.getArtFileNumber(picnum))
    
    def findPicnumFile(self, picnum, regexDefault, texFileMap, userArtTexFileMap=None):
        imgFilePath = None
        
        ## First search for User Art if in User Art range and available
        if (picnum >= TextureImporter.PICNUM_USER_ART_START) and isinstance(userArtTexFileMap, dict) and (len(userArtTexFileMap) > 0):
            ## Try to get User Art file with default filename
            imgFilePath = TextureImporter.getDictValueByKeyRegex(userArtTexFileMap, regexDefault)
            if imgFilePath is None:
                ## A filename matching this regex does not specify the whole picnum and is only acceptable as fallback for User Art:
                regexUserArtFallback = re.compile(r"^0{0,2}%d-.{3}\.(jpg|png)$" % TextureImporter.getArtFileIndex(picnum), re.IGNORECASE)
                imgFilePath = TextureImporter.getDictValueByKeyRegex(userArtTexFileMap, regexUserArtFallback)
                log.debug("Tried to find User Art for picnum %d using fallback RegEx, resulting in: %s" % (picnum, imgFilePath))
        
        ## If we could not get any User Art file, search the normal file map
        if (imgFilePath is None) and isinstance(texFileMap, dict) and (len(texFileMap) > 0):
            imgFilePath = TextureImporter.getDictValueByKeyRegex(texFileMap, regexDefault)
        
        ## If we could still not get any image file, search the User Art file map again in the full picnum range
        ## Normally the User Art folder should only contain textures in the range: picnum >= 3584
        ## But the user might have put textures outside that range there anyway...
        if (imgFilePath is None) and isinstance(userArtTexFileMap, dict) and (len(userArtTexFileMap) > 0):
            imgFilePath = TextureImporter.getDictValueByKeyRegex(userArtTexFileMap, regexDefault)
            if imgFilePath is not None:
                log.debug("Non User Art texture found in User Art folder: %s" % imgFilePath)
        
        return imgFilePath
    
    def __createMaterial(self, picnum) -> Tuple[bpy.types.Material, Optional[PicnumEntry]]:
        matName = self.getMaterialName(picnum)
        existingMat = self.existingMats.get(matName, None)
        regexDefault = re.compile(TextureImporter.getTextureFileNamePattern(picnum), re.IGNORECASE)
        
        picnum_entry = self.picnum_dict.get(picnum, None)
        if not picnum_entry:
            log.debug(f"No picnum_entry for picnum {picnum} found in picnum_dict! Trying with legacy code.")
            img_path_legacy = self.findPicnumFile(picnum, regexDefault, self.texFileMap, self.userArtTexFileMap)
            img_legacy = None
            file_valid = False
            file_size = 0
            if img_path_legacy and os.path.exists(img_path_legacy) and os.path.isfile(img_path_legacy):
                ## Load the image here already, even if we might still be reusing an existing material so this image might not be used.
                ## We should normally not get here anyway if the new texture_importer works correctly and images loaded by the texture_importer might go unused as well in the same way anyway.
                img_legacy = TextureImporter.tryLoadBlenderImage(img_path_legacy, TextureImporter.getImgName(picnum))
                if img_legacy is not None:
                    file_valid = True
                    file_size = os.path.getsize(img_path_legacy)
                    log.debug(f"Legacy Code found image! Path: {img_path_legacy}")
                else:
                    img_path_legacy = None  ## Disregard this file path if loading it was unsuccessful.
            ## Generate a PicnumEntry in any case for the following code to work with and to assign to this material, even if no valid file was found.
            picnum_entry = PicnumEntry(
                tile_index = picnum,
                image = img_legacy,
                file_or_archive_path = img_path_legacy,
                path_is_image_file   = file_valid,
                file_or_entry_length = file_size,
                archive_type         = None,
                art_picanm_available = False
            )
            if img_legacy is not None:
                TextureImporter.write_image_props(img_legacy, picnum_entry)
        
        
        ## Reuse an existing material
        if self.reuseExistingMaterials and (existingMat is not None):
            existing_img = None
            recovered_picnum_entry = None
            reused_picnum_entry = picnum_entry
            reused_size = TextureImporter.DEFAULT_TILE_DIM
            if reused_picnum_entry.image is not None:
                reused_size = reused_picnum_entry.image.size
            
            ## Try to find an image node in the existing material containing a picnum_entry
            for node in existingMat.node_tree.nodes:
                img = getattr(node, "image", None)
                if (node.type == 'TEX_IMAGE') and (img is not None):
                    recovered_picnum_entry = TextureImporter.get_picnum_entry_from_image(img)
                    if recovered_picnum_entry is not None:
                        existing_img = img
                        log.debug(f"Image Node with image name {img.name} found in existing material {matName} by picnum_entry. (picnum:{recovered_picnum_entry.tile_index} center_offset_x:{recovered_picnum_entry.center_offset_x} center_offset_y:{recovered_picnum_entry.center_offset_y} path_with_entry:{recovered_picnum_entry.path_with_entry})")
                        break
            
            if recovered_picnum_entry is None:
                ## Get a list of possible names to check
                image_names_to_check = [TextureImporter.getImgName(picnum), self.getTextureFileNameDefault(picnum)]
                if picnum_entry.image_file_path is not None:
                    image_names_to_check.append(os.path.basename(picnum_entry.image_file_path))
                if picnum_entry.image is not None:
                    image_names_to_check.append(picnum_entry.image.name)
                    if picnum_entry.image.filepath:
                        image_names_to_check.append(os.path.basename(picnum_entry.image.filepath))
                log.debug(f"Checking in existing material {existingMat.name} for names: {image_names_to_check}")
                
                ## Try to find an image node in the existing material with matching image file path or name to get the dimensions and PicnumEntry properties from.
                for node in existingMat.node_tree.nodes:
                    img = getattr(node, "image", None)
                    if (node.type == 'TEX_IMAGE') and (img is not None):
                        img_file_name = os.path.basename(img.filepath) if img.filepath else None
                        if ((img_file_name is not None) and (img_file_name in image_names_to_check)) or (img.name in image_names_to_check):
                            existing_img = img
                            log.debug(f"Image Node with image name {img.name} found in existing material {matName} by name.")
                            break
                        if ((img_file_name is not None) and regexDefault.match(img_file_name)) or regexDefault.match(img.name):
                            existing_img = img
                            log.debug(f"Image Node with image name {img.name} found in existing material {matName} using regex.")
                            break
            
            if existing_img is not None:
                reused_size = existing_img.size
                if recovered_picnum_entry is None:
                    recovered_picnum_entry = TextureImporter.get_picnum_entry_from_image(existing_img)
                if recovered_picnum_entry is not None:
                    reused_picnum_entry = recovered_picnum_entry
                else:
                    reused_picnum_entry.image = existing_img
                    reused_picnum_entry.file_or_entry_length = None
                    existing_img_path = existing_img.filepath
                    if existing_img_path is not None:
                        reused_picnum_entry.file_or_archive_path = existing_img_path
                        reused_picnum_entry.path_is_image_file   = True
            else:
                log.debug(f"Found existing material \"{matName}\" but no matching image node! file_or_archive_path: {picnum_entry.file_or_archive_path}")
            
            self.dimensionsDict[picnum] = reused_size
            self.materialDict[picnum] = (existingMat, reused_picnum_entry)
            return (existingMat, reused_picnum_entry)
        
        
        ## Make sure we have at least a fallback image to work with if no texture is available
        if picnum_entry.image is None:
            picnum_entry.image = bpy.data.images.new(
                name = TextureImporter.getImgName(picnum),
                width = TextureImporter.DEFAULT_TILE_DIM[0],
                height = TextureImporter.DEFAULT_TILE_DIM[1],
                alpha = True,
            )
        
        
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
        nodeImg.image = picnum_entry.image
        nodeImg.location = (-400, 325)
        nodeImg.interpolation = 'Closest' if self.sampleClosestTexel else 'Smart'
        newMat.node_tree.links.new(nodeImg.outputs["Color"], nodePbr.inputs["Base Color"])
        newMat.node_tree.links.new(nodeImg.outputs["Alpha"], nodePbr.inputs["Alpha"])
        
        ## Adding Color Attribute node for shade values
        if self.shadeToVertexColors:
            nodeAttribute = newMat.node_tree.nodes.new(type='ShaderNodeVertexColor')
            nodeAttribute.layer_name = "Shade"
            nodeAttribute.location = (-600, 925)
            
            nodeAttrMix = newMat.node_tree.nodes.new(type='ShaderNodeMixRGB')
            nodeAttrMix.blend_type = 'MULTIPLY'
            nodeAttrMix.inputs["Fac"].default_value = 1
            nodeAttrMix.location = (-200, 925)
                
            newMat.node_tree.links.new(nodeAttribute.outputs["Color"], nodeAttrMix.inputs["Color2"])
            newMat.node_tree.links.new(nodeImg.outputs["Color"], nodeAttrMix.inputs["Color1"])
            newMat.node_tree.links.new(nodeAttrMix.outputs["Color"], nodePbr.inputs["Base Color"])
        
        ## Adding nodes for procedural details
        if self.proceduralMaterialEffects:
            nodeBevel = newMat.node_tree.nodes.new(type='ShaderNodeBevel')
            nodeBevel.samples = 16
            nodeBevel.inputs["Radius"].default_value = 0.03
            
            nodeBump1 = newMat.node_tree.nodes.new(type='ShaderNodeBump')
            nodeBump1.inputs["Strength"].default_value = 0.08
            
            nodeBump2 = newMat.node_tree.nodes.new(type='ShaderNodeBump')
            nodeBump2.inputs["Strength"].default_value = 0.1
            
            if self.blversion[0] < 4 or (self.blversion[0] == 4 and self.blversion[1] < 1):  ## Blender Versions older than 4.1 had a dedicated Musgrave Node
                nodeMusgrave = newMat.node_tree.nodes.new(type='ShaderNodeTexMusgrave')
                nodeMusgrave.inputs["Scale"].default_value = 0.5
                nodeMusgrave.inputs["Detail"].default_value = 15
                nodeMusgrave.inputs["Dimension"].default_value = 1
                nodeMusgrave.inputs["Lacunarity"].default_value = 3
            else:
                nodeMusgrave = newMat.node_tree.nodes.new(type='ShaderNodeTexNoise')
                nodeMusgrave.normalize = False
                nodeMusgrave.inputs["Scale"].default_value = 0.5
                nodeMusgrave.inputs["Detail"].default_value = 14
                nodeMusgrave.inputs["Roughness"].default_value = 0.333333
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
            if self.shadeToVertexColors:
                newMat.node_tree.links.new(nodeAttrMix.outputs["Color"], nodeMix.inputs["Color1"])
            else:
                newMat.node_tree.links.new(nodeImg.outputs["Color"], nodeMix.inputs["Color1"])
            newMat.node_tree.links.new(nodeMix.outputs["Color"], nodePbr.inputs["Base Color"])
        
        self.dimensionsDict[picnum] = picnum_entry.image.size
        self.materialDict[picnum] = (newMat, picnum_entry)
        return (newMat, picnum_entry)

    def getMaterial(self, picnum):
        (mat, picnum_entry) = self.materialDict.get(picnum, (None, None))
        if mat:
            return mat
        else:
            (mat, picnum_entry) = self.__createMaterial(picnum)
            return mat
    
    def hasTexture(self, picnum) -> bool:
        (mat, picnum_entry) = self.materialDict.get(picnum, (None, None))
        if not mat:
            (mat, picnum_entry) = self.__createMaterial(picnum)
        return bool(picnum_entry and picnum_entry.image is not None)
    
    def getDimensions(self, picnum):
        if picnum not in self.materialDict:
            self.__createMaterial(picnum)
        return self.dimensionsDict.get(picnum, TextureImporter.DEFAULT_TILE_DIM)

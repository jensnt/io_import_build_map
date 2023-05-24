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

bl_info = {
    "name": "Import BUILD Map format",
    "author": "Jens Neitzel",
    "version": (1, 1, 0),
    "blender": (2, 93, 0),
    "location": "File > Import > BUILD Map (.map)",
    "description": "Import geometry and materials from a BUILD Map file.",
    "doc_url": "https://github.com/jensnt/io_import_build_map",
    "category": "Import-Export",
}


# To support reload properly, try to access a package var,
# if it's there, reload everything
if "bpy" in locals():
    import importlib
    if "buildmap_format" in locals():
        importlib.reload(buildmap_format)
    if "buildmap_importer" in locals():
        importlib.reload(buildmap_importer)
    if "buildmap_materialmanager" in locals():
        importlib.reload(buildmap_materialmanager)

import logging
import os

import bpy
from bpy_extras.io_utils import ImportHelper

from . import buildmap_format
from . import buildmap_importer
from . import buildmap_materialmanager

log = logging.getLogger(__name__)



class ImportBuildMapPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    textureFolderInvalidText = "The selected texture folder is not a valid folder"
    
    def getTextureFolder(self):
        return bpy.path.abspath(self.get("textureFolder", ''))
    
    def setTextureFolder(self, value):
        if os.path.isdir(value):
            self["textureFolder"] = value
        else:
            log.error(textureFolderInvalidText)
            self["textureFolder"] = textureFolderInvalidText
    
    def getUaTextureFolder(self):
        return bpy.path.abspath(self.get("userArtTextureFolder", ''))
    
    def setUaTextureFolder(self, value):
        if os.path.isdir(value):
            self["userArtTextureFolder"] = value
        else:
            log.error(textureFolderInvalidText)
            self["userArtTextureFolder"] = textureFolderInvalidText
    
    textureFolder : bpy.props.StringProperty(
        name = "Texture folder",
        default = "",
        description = "Select a folder that contains your textures",
        subtype = 'DIR_PATH',
        get = getTextureFolder,
        set = setTextureFolder)
    
    userArtTextureFolder : bpy.props.StringProperty(
        name = "Custom User Art Texture folder",
        default = "",
        description = "Select an optional folder for Custom User Art Textures. "
                      "This folder will take preference over the normal Texture folder in the User Art Range. "
                      "(The User Art Range starts with picnum 3584, which is 000-014.png)",
        subtype = 'DIR_PATH',
        get = getUaTextureFolder,
        set = setUaTextureFolder)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "textureFolder")
        layout.prop(self, "userArtTextureFolder")



class ImportBuildMap(bpy.types.Operator, ImportHelper):
    bl_idname = "import_build.map"
    bl_label = "Import BUILD Map"
    bl_description = "Import a BUILD Map"
    bl_options = {'UNDO'}
    
    filename_ext = ".map"
    
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default="*.map", options={'HIDDEN'})
    
    objectPrefix : bpy.props.StringProperty(
        name="Object Prefix",
        description = ("Optional Prefix for created Objects"),
        default = "")
    splitSectors : bpy.props.BoolProperty(
        name="Split Sectors",
        description = ("Create a separete object for every Sector. "
                       "This will also store custom properties in every Sector Object"),
        default = False)
    splitWalls : bpy.props.BoolProperty(
        name="Split Walls",
        description = ("Create a separete object for every Wall. "
                       "This will also store custom properties in every Wall Object"),
        default = False)
    splitSky : bpy.props.BoolProperty(
        name="Split Sky",
        description = ("Create separete objects for ceilings and walls representing the sky"),
        default = True)
    scaleSpritesLikeInGame : bpy.props.BoolProperty(
        name="Scale Sprites as in Game",
        description = ("Some special Sprites (e.g. weapons and ammo) are always the same fixed scale in game "
                       "even though they might be scaled differently in the map editor. "
                       "If this option is set, those sprites are scaled like in the game"),
        default = True)
    wallSpriteOffset : bpy.props.FloatProperty(
        name="Wall Sprite Offset",
        description = ("Separates wall sprites from walls by this offset"),
        default = 0,
        unit = 'LENGTH')
    useUserArt : bpy.props.BoolProperty(
        name="Use Custom User Art",
        description = ("Use Custom User Art Textures if the optional Custom User Art folder is configured. "
                       "These textures will take preference over the normal Texture folder in the User Art Range. "
                       "(The User Art Range starts with picnum 3584, which is 000-014.png)"),
        default = True)
    reuseExistingMaterials : bpy.props.BoolProperty(
        name="Reuse Materials",
        description = ("Reuse existing materials"),
        default = True)
    sampleClosestTexel : bpy.props.BoolProperty(
        name="Pixel Shading",
        description = ("Sample closest texel on textures instead of interpolating"),
        default = True)
    proceduralMaterialEffects : bpy.props.BoolProperty(
        name="Procedural Material Effects",
        description = ("Adding nodes in created materials to achieve a more realistic appearance"),
        default = False)
    useBackfaceCulling : bpy.props.BoolProperty(
        name="Use Back Face Culling",
        description = ("Use back face culling to hide the back side of faces"),
        default = False)
    ignoreErrors : bpy.props.BoolProperty(
        name="Ignore Map Errors",
        description = ("Try to continue parsing a corrupted map file. Corrupted Sectors will be skipped"),
        default = False)
    
    textureFolder = None
    userArtTextureFolder = None
    
    def execute(self, context):
        wm = context.window_manager
        wm.progress_begin(0, 1)
        wm.progress_update(0)
        
        addon_prefs = context.preferences.addons[__name__].preferences
        if addon_prefs.textureFolder == "":
            log.debug("The texture folder is not set in preferences.")
        elif addon_prefs.textureFolder == ImportBuildMapPreferences.textureFolderInvalidText:
            log.debug("The texture folder is set invalid in preferences.")
        else:
            log.debug("The texture folder is set to: %s" % addon_prefs.textureFolder)
            self.textureFolder = addon_prefs.textureFolder
        
        if self.useUserArt:
            if addon_prefs.userArtTextureFolder == "":
                log.debug("The user art texture folder is not set in preferences.")
            elif addon_prefs.userArtTextureFolder == ImportBuildMapPreferences.textureFolderInvalidText:
                log.debug("The user art texture folder is set invalid in preferences.")
            else:
                log.debug("The user art texture folder is set to: %s" % addon_prefs.userArtTextureFolder)
                self.userArtTextureFolder = addon_prefs.userArtTextureFolder
        
        if (self.textureFolder is None) and (self.userArtTextureFolder is None):
            log.warning("No Texture Folder specified. Materials will be black. Specify in: Edit > Preferences > Add-ons > Import-Export: Import BUILD Map format")
            self.report({'WARNING'}, "No Texture Folder specified. Materials will be black. Specify in: Edit > Preferences > Add-ons > Import-Export: Import BUILD Map format")
        
        try:
            bmap = buildmap_format.BuildMap(self.filepath, self.ignoreErrors)
        except ValueError as e:
            self.report({'ERROR'}, 'Parsing file failed! %s'%str(e))
        except:
            log.error("Parsing file failed!")
            self.report({'ERROR'}, 'Parsing file failed!')
        else:
            mapCollection = bpy.data.collections.new(os.path.basename(self.filepath))
            context.collection.children.link(mapCollection)
            matManager = buildmap_materialmanager.materialManager(self.textureFolder, self.userArtTextureFolder, self.reuseExistingMaterials, self.sampleClosestTexel, self.proceduralMaterialEffects, self.useBackfaceCulling)
            prefix = f"{self.objectPrefix}_" if self.objectPrefix else ""
            importer = buildmap_importer.BuildMapImporter(bmap, matManager, context, mapCollection, prefix)
            importer.addSpawn()
            importer.addSprites(self.wallSpriteOffset, self.scaleSpritesLikeInGame)
            importer.addMapGeometry(self.splitSectors, self.splitWalls, self.splitSky)
            log.debug("Number of Materials: %s" % len(matManager.materialDict))
        
        wm.progress_end()
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.fileselect_add(self)
        return {'RUNNING_MODAL'}


def menu_import(self, context):
    self.layout.operator(ImportBuildMap.bl_idname, text="BUILD Map (.map)")

def register():
    bpy.utils.register_class(ImportBuildMap)
    bpy.types.TOPBAR_MT_file_import.append(menu_import)
    bpy.utils.register_class(ImportBuildMapPreferences)

def unregister():
    bpy.utils.unregister_class(ImportBuildMapPreferences)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    bpy.utils.unregister_class(ImportBuildMap)

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
    "version": (1, 3, 0),
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

from .buildmap_format import BuildMapFactory as BuildMap
from . import buildmap_importer
from . import buildmap_materialmanager

log = logging.getLogger(__package__)



class ImportBuildMapPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    textureFolderInvalidText = "The selected texture folder is not a valid folder"
    
    def getTextureFolder(self):
        return bpy.path.abspath(self.get("textureFolder", ''))
    
    def setTextureFolder(self, value):
        if os.path.isdir(value):
            self["textureFolder"] = value
        else:
            log.error(self.textureFolderInvalidText)
            self["textureFolder"] = self.textureFolderInvalidText
    
    def getUaTextureFolder(self):
        return bpy.path.abspath(self.get("userArtTextureFolder", ''))
    
    def setUaTextureFolder(self, value):
        if os.path.isdir(value):
            self["userArtTextureFolder"] = value
        else:
            log.error(self.textureFolderInvalidText)
            self["userArtTextureFolder"] = self.textureFolderInvalidText
    
    def getBloodTextureFolder(self):
        return bpy.path.abspath(self.get("bloodTextureFolder", ''))
    
    def setBloodTextureFolder(self, value):
        if os.path.isdir(value):
            self["bloodTextureFolder"] = value
        else:
            log.error(self.textureFolderInvalidText)
            self["bloodTextureFolder"] = self.textureFolderInvalidText
    
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
    
    bloodTextureFolder : bpy.props.StringProperty(
        name = "Blood Texture folder",
        default = "",
        description = "Select a folder that contains your Blood textures. "
                      "If left empty, the other folders will be used for Blood maps",
        subtype = 'DIR_PATH',
        get = getBloodTextureFolder,
        set = setBloodTextureFolder)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "textureFolder")
        layout.prop(self, "userArtTextureFolder")
        layout.prop(self, "bloodTextureFolder")



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
        description = ("This option specifies a prefix that will be used in the name of every imported object"),
        default = "")
    splitSectors : bpy.props.BoolProperty(
        name="Split Sectors",
        description = ("If enabled, the floor and ceiling of every sector will be split off into separate objects.\n"
                       "This is necessary to import custom properties from BUILD-Map structures for sectors"),
        default = False)
    splitWalls : bpy.props.BoolProperty(
        name="Split Walls",
        description = ("If enabled, walls will be split off into separate objects.\n"
                       "This is necessary to import custom properties from BUILD-Map structures for walls"),
        default = False)
    splitSky : bpy.props.BoolProperty(
        name="Split Sky",
        description = ("If enabled, floors and ceilings with parallaxing enabled and associated walls will be split off into separate objects and sorted into the \"Sky\" collection"),
        default = True)
    scaleSpritesLikeInGame : bpy.props.BoolProperty(
        name="Scale Sprites as in Game",
        description = ("Some special sprites (e.g. weapons and ammo) can have a different scale in game compared to map editors.\n"
                       "If this option is enabled, the importer will try to scale them as they appear in game"),
        default = True)
    wallSpriteOffset : bpy.props.FloatProperty(
        name="Wall Sprite Offset",
        description = ("Separate wall sprites from walls as specified by this offset.\n"
                       "This is useful to avoid Z-fighting.\n"
                       "A small offset like 0.01 m is enough in many cases"),
        default = 0,
        unit = 'LENGTH')
    useUserArt : bpy.props.BoolProperty(
        name="Use Custom User Art",
        description = ("If a Custom User Art texture folder is specified in the Add-on preferences you can use this option to enable or disable the usage of Custom User Art textures.\n"
                       "These textures will take preference over the normal Texture folder within the User Art Range.\n"
                       "The User Art Range starts with picnum 3584, which is \"000-014.png\""),
        default = True)
    reuseExistingMaterials : bpy.props.BoolProperty(
        name="Reuse Materials",
        description = ("If enabled, materials that already exist in the blend file, having the same name as this Add-on would create, will be reused instead of creating new ones.\n"
                       "If disabled, new materials will be created with a suffix"),
        default = True)
    shadeToVertexColors : bpy.props.BoolProperty(
        name="Shade to Vertex Colors",
        description = ("Save Ceiling, Floor, Wall and Sprite Shade values as Vertex Color Attributes and use those in created Materials"),
        default = True)
    sampleClosestTexel : bpy.props.BoolProperty(
        name="Pixel Shading",
        description = ("If enabled, textures will render with hard pixel edges instead of interpolation"),
        default = True)
    proceduralMaterialEffects : bpy.props.BoolProperty(
        name="Procedural Material Effects",
        description = ("If enabled, additional shader nodes will be created in materials to add procedural details.\n"
                       "This works best with \"Pixel Shading\" disabled"),
        default = False)
    useBackfaceCulling : bpy.props.BoolProperty(
        name="Use Back Face Culling",
        description = ("If enabled, use back-face culling in created materials to hide the back side of faces"),
        default = False)
    heuristicWallSearch : bpy.props.BoolProperty(
        name="Heuristic Wall Search",
        description = ("Try to find neighboring walls between sectors based on their position.\n"
                       "This might fix errors in the map but can also introduce errors"),
        default = False)
    ignoreErrors : bpy.props.BoolProperty(
        name="Ignore Map Errors",
        description = ("If you encounter a corrupted map that gives you errors where for example the number of walls appears incorrect, you can try this option.\n"
                       "The importer will try to skip corrupted parts of the map.\n"
                       "No guarantee for success, though"),
        default = False)
    
    textureFolder = None
    userArtTextureFolder = None
    bloodTextureFolder = None
    
    def execute(self, context):
        wm = context.window_manager
        wm.progress_begin(0, 1)
        wm.progress_update(0)
        addon_prefs = context.preferences.addons[__package__].preferences
        
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
        
        if addon_prefs.bloodTextureFolder == "":
            log.debug("The Blood texture folder is not set in preferences.")
        elif addon_prefs.bloodTextureFolder == ImportBuildMapPreferences.textureFolderInvalidText:
            log.debug("The Blood texture folder is set invalid in preferences.")
        else:
            log.debug("The Blood texture folder is set to: %s" % addon_prefs.bloodTextureFolder)
            self.bloodTextureFolder = addon_prefs.bloodTextureFolder
        
        if (self.textureFolder is None) and (self.userArtTextureFolder is None) and (self.bloodTextureFolder is None):
            log.warning("No Texture Folder specified. Materials will be black. Specify in: Edit > Preferences > Add-ons > Import-Export: Import BUILD Map format")
            self.report({'WARNING'}, "No Texture Folder specified. Materials will be black. Specify in: Edit > Preferences > Add-ons > Import-Export: Import BUILD Map format")
        
        try:
            bmap = BuildMap(self.filepath, self.heuristicWallSearch, self.ignoreErrors)
        except ValueError as e:
            self.report({'ERROR'}, 'Parsing file failed! %s'%str(e))
            return {'CANCELLED'}
        except Exception as e:
            log.error("Parsing file failed!", exc_info=True)
            self.report({'ERROR'}, f"Parsing file failed! Exception: {e}")
            return {'CANCELLED'}
        else:
            mapCollection = bpy.data.collections.new(os.path.basename(self.filepath))
            context.collection.children.link(mapCollection)
            matManager = buildmap_materialmanager.materialManager(
                bmap,
                self.textureFolder,
                self.userArtTextureFolder,
                self.bloodTextureFolder,
                self.reuseExistingMaterials,
                self.sampleClosestTexel,
                self.shadeToVertexColors,
                self.proceduralMaterialEffects,
                self.useBackfaceCulling
            )
            prefix = f"{self.objectPrefix}_" if self.objectPrefix else ""
            importer = buildmap_importer.BuildMapImporter(bmap, matManager, context, mapCollection, prefix)
            importer.addSpawn()
            importer.addSprites(self.wallSpriteOffset, self.scaleSpritesLikeInGame, self.shadeToVertexColors)
            importer.addMapGeometry(self.splitSectors, self.splitWalls, self.splitSky, self.shadeToVertexColors)
            log.debug("Number of Materials: %s" % len(matManager.materialDict))
            wm.progress_update(1)
            return {'FINISHED'}
        finally:
            wm.progress_end()

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

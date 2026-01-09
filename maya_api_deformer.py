"""
Maya OpenMaya 2.0 Custom Deformer

Demonstrates the Maya Python API 2.0 for creating a custom
deformer node with proper registration and attribute setup.
"""
from __future__ import annotations

import math
from typing import Any

import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma


def maya_useNewAPI() -> None:
    """Indicate this plugin uses Maya Python API 2.0."""
    pass


class WaveDeformer(om.MPxDeformerNode):
    """
    Custom wave deformer that creates sinusoidal displacement.

    Attributes:
        amplitude: Height of the wave
        wavelength: Distance between wave peaks
        phase: Offset of the wave pattern
        direction: Axis of wave propagation (0=X, 1=Y, 2=Z)
    """

    TYPE_NAME = "waveDeformer"
    TYPE_ID = om.MTypeId(0x00127800)

    amplitude_attr: om.MObject
    wavelength_attr: om.MObject
    phase_attr: om.MObject
    direction_attr: om.MObject
    time_attr: om.MObject

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    def creator(cls) -> WaveDeformer:
        """Create an instance of the deformer."""
        return cls()

    @classmethod
    def initialize(cls) -> None:
        """Initialize node attributes."""
        numeric_attr = om.MFnNumericAttribute()
        enum_attr = om.MFnEnumAttribute()
        unit_attr = om.MFnUnitAttribute()

        cls.amplitude_attr = numeric_attr.create(
            "amplitude", "amp", om.MFnNumericData.kFloat, 1.0
        )
        numeric_attr.keyable = True
        numeric_attr.storable = True
        numeric_attr.writable = True
        numeric_attr.setMin(0.0)
        numeric_attr.setSoftMax(10.0)

        cls.wavelength_attr = numeric_attr.create(
            "wavelength", "wl", om.MFnNumericData.kFloat, 5.0
        )
        numeric_attr.keyable = True
        numeric_attr.storable = True
        numeric_attr.writable = True
        numeric_attr.setMin(0.001)
        numeric_attr.setSoftMax(50.0)

        cls.phase_attr = numeric_attr.create(
            "phase", "ph", om.MFnNumericData.kFloat, 0.0
        )
        numeric_attr.keyable = True
        numeric_attr.storable = True
        numeric_attr.writable = True

        cls.direction_attr = enum_attr.create("direction", "dir", 0)
        enum_attr.addField("X", 0)
        enum_attr.addField("Y", 1)
        enum_attr.addField("Z", 2)
        enum_attr.keyable = True
        enum_attr.storable = True
        enum_attr.writable = True

        cls.time_attr = unit_attr.create(
            "time", "tm", om.MFnUnitAttribute.kTime, 0.0
        )
        unit_attr.keyable = True
        unit_attr.storable = True
        unit_attr.writable = True

        cls.addAttribute(cls.amplitude_attr)
        cls.addAttribute(cls.wavelength_attr)
        cls.addAttribute(cls.phase_attr)
        cls.addAttribute(cls.direction_attr)
        cls.addAttribute(cls.time_attr)

        output_geom = om.MPxDeformerNode.outputGeom
        cls.attributeAffects(cls.amplitude_attr, output_geom)
        cls.attributeAffects(cls.wavelength_attr, output_geom)
        cls.attributeAffects(cls.phase_attr, output_geom)
        cls.attributeAffects(cls.direction_attr, output_geom)
        cls.attributeAffects(cls.time_attr, output_geom)

    def deform(
        self,
        data_block: om.MDataBlock,
        geo_iter: om.MItGeometry,
        matrix: om.MMatrix,
        multi_index: int,
    ) -> None:
        """
        Compute the deformation for each vertex.

        Args:
            data_block: The node's data block
            geo_iter: Iterator for geometry points
            matrix: Local-to-world transformation matrix
            multi_index: Index of the geometry being deformed
        """
        envelope = data_block.inputValue(self.envelope).asFloat()
        if envelope == 0.0:
            return

        amplitude = data_block.inputValue(self.amplitude_attr).asFloat()
        wavelength = data_block.inputValue(self.wavelength_attr).asFloat()
        phase = data_block.inputValue(self.phase_attr).asFloat()
        direction = data_block.inputValue(self.direction_attr).asShort()
        time = data_block.inputValue(self.time_attr).asTime().value

        input_handle = data_block.outputArrayValue(self.input)
        input_handle.jumpToElement(multi_index)
        input_element = input_handle.outputValue()
        input_geom = input_element.child(self.inputGeom).asMesh()
        mesh_fn = om.MFnMesh(input_geom)

        time_offset = time * 0.1

        while not geo_iter.isDone():
            point = geo_iter.position()
            weight = self.weightValue(data_block, multi_index, geo_iter.index())

            if direction == 0:
                distance = point.x
            elif direction == 1:
                distance = point.y
            else:
                distance = point.z

            wave_value = math.sin((distance / wavelength + phase + time_offset) * 2 * math.pi)
            displacement = wave_value * amplitude * envelope * weight

            if direction == 0:
                point.y += displacement
            elif direction == 1:
                point.z += displacement
            else:
                point.y += displacement

            geo_iter.setPosition(point)
            geo_iter.next()


class NoiseDeformer(om.MPxDeformerNode):
    """
    Procedural noise-based deformer using simple Perlin-like noise.

    Attributes:
        strength: Intensity of the noise displacement
        frequency: Scale of the noise pattern
        seed: Random seed for noise generation
    """

    TYPE_NAME = "noiseDeformer"
    TYPE_ID = om.MTypeId(0x00127801)

    strength_attr: om.MObject
    frequency_attr: om.MObject
    seed_attr: om.MObject

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    def creator(cls) -> NoiseDeformer:
        return cls()

    @classmethod
    def initialize(cls) -> None:
        numeric_attr = om.MFnNumericAttribute()

        cls.strength_attr = numeric_attr.create(
            "strength", "str", om.MFnNumericData.kFloat, 0.5
        )
        numeric_attr.keyable = True
        numeric_attr.storable = True
        numeric_attr.setMin(0.0)
        numeric_attr.setSoftMax(5.0)

        cls.frequency_attr = numeric_attr.create(
            "frequency", "freq", om.MFnNumericData.kFloat, 1.0
        )
        numeric_attr.keyable = True
        numeric_attr.storable = True
        numeric_attr.setMin(0.01)
        numeric_attr.setSoftMax(10.0)

        cls.seed_attr = numeric_attr.create(
            "seed", "sd", om.MFnNumericData.kInt, 42
        )
        numeric_attr.keyable = True
        numeric_attr.storable = True

        cls.addAttribute(cls.strength_attr)
        cls.addAttribute(cls.frequency_attr)
        cls.addAttribute(cls.seed_attr)

        output_geom = om.MPxDeformerNode.outputGeom
        cls.attributeAffects(cls.strength_attr, output_geom)
        cls.attributeAffects(cls.frequency_attr, output_geom)
        cls.attributeAffects(cls.seed_attr, output_geom)

    def _simple_noise(self, x: float, y: float, z: float, seed: int) -> float:
        """Generate simple pseudo-random noise value."""
        n = int(x * 73 + y * 179 + z * 283 + seed * 997)
        n = (n << 13) ^ n
        return 1.0 - ((n * (n * n * 15731 + 789221) + 1376312589) & 0x7FFFFFFF) / 1073741824.0

    def deform(
        self,
        data_block: om.MDataBlock,
        geo_iter: om.MItGeometry,
        matrix: om.MMatrix,
        multi_index: int,
    ) -> None:
        envelope = data_block.inputValue(self.envelope).asFloat()
        if envelope == 0.0:
            return

        strength = data_block.inputValue(self.strength_attr).asFloat()
        frequency = data_block.inputValue(self.frequency_attr).asFloat()
        seed = data_block.inputValue(self.seed_attr).asInt()

        input_handle = data_block.outputArrayValue(self.input)
        input_handle.jumpToElement(multi_index)
        input_element = input_handle.outputValue()
        input_geom = input_element.child(self.inputGeom).asMesh()
        mesh_fn = om.MFnMesh(input_geom)
        normals = mesh_fn.getVertexNormals(False)

        while not geo_iter.isDone():
            idx = geo_iter.index()
            point = geo_iter.position()
            weight = self.weightValue(data_block, multi_index, idx)

            px = point.x * frequency
            py = point.y * frequency
            pz = point.z * frequency

            noise_value = self._simple_noise(px, py, pz, seed)
            displacement = noise_value * strength * envelope * weight

            normal = normals[idx]
            point.x += normal.x * displacement
            point.y += normal.y * displacement
            point.z += normal.z * displacement

            geo_iter.setPosition(point)
            geo_iter.next()


def initializePlugin(plugin: om.MObject) -> None:
    """Register plugin nodes with Maya."""
    plugin_fn = om.MFnPlugin(plugin, "Dilen Shah", "1.0.0")

    try:
        plugin_fn.registerNode(
            WaveDeformer.TYPE_NAME,
            WaveDeformer.TYPE_ID,
            WaveDeformer.creator,
            WaveDeformer.initialize,
            om.MPxNode.kDeformerNode,
        )
    except Exception as e:
        om.MGlobal.displayError(f"Failed to register {WaveDeformer.TYPE_NAME}: {e}")

    try:
        plugin_fn.registerNode(
            NoiseDeformer.TYPE_NAME,
            NoiseDeformer.TYPE_ID,
            NoiseDeformer.creator,
            NoiseDeformer.initialize,
            om.MPxNode.kDeformerNode,
        )
    except Exception as e:
        om.MGlobal.displayError(f"Failed to register {NoiseDeformer.TYPE_NAME}: {e}")


def uninitializePlugin(plugin: om.MObject) -> None:
    """Deregister plugin nodes from Maya."""
    plugin_fn = om.MFnPlugin(plugin)

    try:
        plugin_fn.deregisterNode(WaveDeformer.TYPE_ID)
    except Exception as e:
        om.MGlobal.displayError(f"Failed to deregister {WaveDeformer.TYPE_NAME}: {e}")

    try:
        plugin_fn.deregisterNode(NoiseDeformer.TYPE_ID)
    except Exception as e:
        om.MGlobal.displayError(f"Failed to deregister {NoiseDeformer.TYPE_NAME}: {e}")

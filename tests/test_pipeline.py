from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
import unittest

import cv2
import numpy as np

from plot2svg.config import PipelineConfig
from plot2svg.pipeline import PipelineArtifacts, _assemble_scene_graph, _build_region_vector_ignore_mask, _choose_processing_sources, _collect_icon_cleanup_node_ids, _configure_cv_runtime_stability, _detect_container_detail_regions, _detect_panel_arrow_regions, _detect_raster_objects, _erase_region_nodes, _extract_icon_objects, _filter_region_objects, _filter_stroke_scene_graph, _heal_masked_stage_image, _inpaint_node_and_icon_regions, _inject_network_container_object, _inject_panel_background_regions, _maybe_debug_mask_path, _maybe_write_debug_image, _promote_svg_template_nodes, _proposals_for_stage, _prune_region_nodes_by_mask, _resolve_semantic_raster_objects, _should_inpaint_stroke_node, run_pipeline
from plot2svg.analyze import AnalysisResult
from plot2svg.scene_graph import IconObject, NodeObject, RasterObject, RegionObject, SceneGraph, SceneNode


def _run_pipeline_isolated(config: PipelineConfig) -> PipelineArtifacts:
    repo_root = Path(__file__).resolve().parents[1]
    code = (
        "import json, sys; "
        "from pathlib import Path; "
        "from plot2svg.config import PipelineConfig; "
        "from plot2svg.pipeline import run_pipeline; "
        "cfg = PipelineConfig(input_path=Path(sys.argv[1]), output_dir=Path(sys.argv[2])); "
        "artifacts = run_pipeline(cfg); "
        "print(json.dumps({"
        "'analyze_path': str(artifacts.analyze_path), "
        "'enhanced_path': str(artifacts.enhanced_path), "
        "'scene_graph_path': str(artifacts.scene_graph_path), "
        "'final_svg_path': str(artifacts.final_svg_path)}))"
    )
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code, str(config.input_path), str(config.output_dir)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    payload = json.loads(lines[-1])
    return PipelineArtifacts(
        analyze_path=Path(payload["analyze_path"]),
        enhanced_path=Path(payload["enhanced_path"]),
        scene_graph_path=Path(payload["scene_graph_path"]),
        final_svg_path=Path(payload["final_svg_path"]),
    )


class PipelineTest(unittest.TestCase):
    def test_configure_cv_runtime_stability_disables_unsafe_parallelism(self) -> None:
        cv2.setNumThreads(4)
        cv2.ocl.setUseOpenCL(True)

        _configure_cv_runtime_stability()

        self.assertEqual(cv2.getNumThreads(), 1)
        self.assertFalse(cv2.ocl.useOpenCL())

    def test_maybe_write_debug_image_respects_emit_debug_artifacts_flag(self) -> None:
        output_dir = Path("outputs/test-pipeline-debug-toggle")
        image_path = output_dir / "debug.png"
        image = np.full((10, 10, 3), 255, dtype=np.uint8)

        cfg = PipelineConfig(input_path="picture/F2.png", output_dir=output_dir, emit_debug_artifacts=False)
        _maybe_write_debug_image(cfg, image_path, image)

        self.assertFalse(image_path.exists())

    def test_maybe_debug_mask_path_returns_none_when_debug_disabled(self) -> None:
        cfg = PipelineConfig(input_path="picture/F2.png", output_dir="outputs/F2", emit_debug_artifacts=False)

        self.assertIsNone(_maybe_debug_mask_path(cfg, Path("outputs/F2/debug_lines_mask.png")))

    def test_collect_icon_cleanup_node_ids_includes_svg_template_regions(self) -> None:
        stage1_graph = SceneGraph(
            width=220,
            height=180,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 220, 180], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(
                    id='region-template-1',
                    type='region',
                    bbox=[20, 20, 90, 90],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    shape_hint='svg_template',
                    component_role='svg_template:document',
                ),
            ],
        )

        cleanup_ids = _collect_icon_cleanup_node_ids(
            stage1_graph,
            node_objects=[NodeObject(id='node-1', node_id='circle-1', center=[120.0, 60.0], radius=10.0)],
            raster_objects=[RasterObject(id='raster-1', node_id='region-raster-1', bbox=[100, 100, 150, 150], image_href='data:image/png;base64,AAAA')],
        )

        self.assertEqual(cleanup_ids, {'circle-1', 'region-raster-1', 'region-template-1'})

    def test_assemble_scene_graph_keeps_stage1_svg_template_region_without_raster_fallback(self) -> None:
        stage1_graph = SceneGraph(
            width=240,
            height=180,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 240, 180], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(
                    id='region-template-1',
                    type='region',
                    bbox=[20, 20, 90, 90],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    shape_hint='svg_template',
                    component_role='svg_template:document',
                ),
                SceneNode(
                    id='region-plain-1',
                    type='region',
                    bbox=[120, 20, 136, 36],
                    z_index=2,
                    vector_mode='region_path',
                    confidence=0.9,
                    shape_hint='vector_candidate',
                ),
            ],
        )
        stage2_graph = SceneGraph(
            width=240,
            height=180,
            nodes=[SceneNode(id='background-root', type='background', bbox=[0, 0, 240, 180], z_index=0, vector_mode='region_path', confidence=1.0)],
        )
        stage3_graph = SceneGraph(
            width=240,
            height=180,
            nodes=[SceneNode(id='background-root', type='background', bbox=[0, 0, 240, 180], z_index=0, vector_mode='region_path', confidence=1.0)],
        )

        scene_graph = _assemble_scene_graph(
            240,
            180,
            stage1_graph,
            stage2_graph,
            stage3_graph,
            text_nodes=[],
            node_objects=[],
            raster_objects=[],
            stroke_primitives=[],
        )

        node_ids = {node.id for node in scene_graph.nodes}
        self.assertIn('region-template-1', node_ids)
        self.assertNotIn('region-plain-1', node_ids)

    def test_extract_icon_objects_promotes_raster_candidate_to_evenodd_icon(self) -> None:
        image = np.full((140, 120, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 10), (90, 110), (0, 0, 0), -1)
        cv2.rectangle(image, (28, 18), (82, 102), (255, 255, 255), -1)
        cv2.rectangle(image, (35, 25), (75, 35), (0, 0, 0), -1)

        scene_graph = SceneGraph(
            width=120,
            height=140,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 120, 140], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-icon-1', type='region', bbox=[20, 10, 90, 110], z_index=1, vector_mode='region_path', confidence=0.9, shape_hint='raster_candidate'),
            ],
        )
        raster_objects = [
            RasterObject(id='raster-icon-1', node_id='region-icon-1', bbox=[20, 10, 90, 110], image_href='data:image/png;base64,AAAA', metadata={'shape_hint': 'raster_candidate'})
        ]

        icon_objects, kept_rasters = _extract_icon_objects(image, scene_graph, raster_objects)

        self.assertEqual(kept_rasters, [])
        self.assertEqual(len(icon_objects), 1)
        self.assertIsInstance(icon_objects[0], IconObject)
        self.assertEqual(icon_objects[0].fill_rule, 'evenodd')
        self.assertGreaterEqual(icon_objects[0].compound_path.count('M '), 2)


    def test_detect_raster_objects_forces_icon_cluster_into_raster_path(self) -> None:
        image = np.full((140, 120, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 10), (90, 110), (0, 0, 0), -1)
        cv2.rectangle(image, (28, 18), (82, 102), (255, 255, 255), -1)

        scene_graph = SceneGraph(
            width=120,
            height=140,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 120, 140], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-icon-cluster', type='region', bbox=[20, 10, 90, 110], z_index=1, vector_mode='region_path', confidence=0.9, shape_hint='icon_cluster'),
            ],
        )

        raster_objects = _detect_raster_objects(image, image.copy(), scene_graph, excluded_node_ids=set())

        self.assertEqual(len(raster_objects), 1)
        self.assertEqual(raster_objects[0].metadata.get('shape_hint'), 'icon_cluster')

    def test_extract_icon_objects_promotes_icon_cluster_to_evenodd_icon(self) -> None:
        image = np.full((140, 120, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 10), (90, 110), (0, 0, 0), -1)
        cv2.rectangle(image, (28, 18), (82, 102), (255, 255, 255), -1)
        cv2.rectangle(image, (35, 25), (75, 35), (0, 0, 0), -1)

        scene_graph = SceneGraph(
            width=120,
            height=140,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 120, 140], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-icon-cluster', type='region', bbox=[20, 10, 90, 110], z_index=1, vector_mode='region_path', confidence=0.9, shape_hint='icon_cluster'),
            ],
        )
        raster_objects = [
            RasterObject(id='raster-icon-cluster', node_id='region-icon-cluster', bbox=[20, 10, 90, 110], image_href='data:image/png;base64,AAAA', metadata={'shape_hint': 'icon_cluster'})
        ]

        icon_objects, kept_rasters = _extract_icon_objects(image, scene_graph, raster_objects)

        self.assertEqual(kept_rasters, [])
        self.assertEqual(len(icon_objects), 1)
        self.assertEqual(icon_objects[0].fill_rule, 'evenodd')
        self.assertGreaterEqual(icon_objects[0].compound_path.count('M '), 2)

    def test_run_pipeline_promotes_slice_b_icon_into_icon_objects(self) -> None:
        config = PipelineConfig(
            input_path=Path('sandbox/slice_B_icon.png'),
            output_dir=Path('outputs/round366-slice-b-icon'),
        )

        artifacts = _run_pipeline_isolated(config)
        data = json.loads(artifacts.scene_graph_path.read_text(encoding='utf-8'))

        self.assertTrue(data.get('icon_objects'))
        icon = data['icon_objects'][0]
        x1, y1, x2, y2 = icon['bbox']
        self.assertGreaterEqual(x2 - x1, 60)
        self.assertGreaterEqual(y2 - y1, 80)
        self.assertIn("class='icon-object'", artifacts.final_svg_path.read_text(encoding='utf-8'))


    def test_run_pipeline_accepts_unicode_input_path(self) -> None:
        output_dir = Path('outputs/pipeline-unicode-input')
        self.addCleanup(shutil.rmtree, output_dir, ignore_errors=True)
        config = PipelineConfig(
            input_path=Path('picture/新建文件夹/d656b8bc-f179-4147-adc5-892858e4d8e7.png'),
            output_dir=output_dir,
        )

        artifacts = _run_pipeline_isolated(config)

        self.assertTrue(artifacts.scene_graph_path.exists())
        self.assertTrue(artifacts.final_svg_path.exists())

    def test_small_lowres_routes_use_original_for_proposals_and_scaled_vector_source(self) -> None:
        config = PipelineConfig(input_path=Path("picture/orr_signature.png"), output_dir=Path("outputs/orr_signature"))
        analysis = AnalysisResult(
            width=635,
            height=568,
            aspect_ratio=635 / 568,
            color_complexity=0.1,
            edge_density=0.01,
            alpha_present=False,
            route_type="small_lowres",
            should_tile=False,
            should_super_resolve=True,
        )

        proposal_source, vector_source, vector_scale = _choose_processing_sources(
            config,
            analysis,
            Path("outputs/orr_signature/enhanced.png"),
            2.0,
        )

        self.assertEqual(proposal_source, config.input_path)
        self.assertEqual(vector_source, Path("outputs/orr_signature/enhanced.png"))
        self.assertEqual(vector_scale, 2.0)

    def test_run_pipeline_returns_artifact_paths(self) -> None:
        config = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"))
        artifacts = _run_pipeline_isolated(config)
        self.assertEqual(artifacts.analyze_path.name, "analyze.json")
        self.assertEqual(artifacts.enhanced_path.name, "enhanced.png")
        self.assertEqual(artifacts.scene_graph_path.name, "scene_graph.json")
        self.assertEqual(artifacts.final_svg_path.name, "final.svg")
        self.assertTrue((config.output_dir / "proposal_text_mask.png").exists())
        self.assertTrue((config.output_dir / "proposal_graphic_layer.png").exists())
        self.assertTrue((config.output_dir / "vector_text_mask.png").exists())
        self.assertTrue((config.output_dir / "vector_graphic_layer.png").exists())
        data = json.loads(artifacts.scene_graph_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["nodes"]), 2)
        self.assertLess(len(data["nodes"]), 400)
        self.assertTrue(any(node["type"] == "region" for node in data["nodes"]))
        self.assertTrue(any(node["type"] == "stroke" for node in data["nodes"]))
        self.assertLessEqual(sum(1 for node in data["nodes"] if node.get("shape_hint") == "circle"), 6)

    def test_small_lowres_pipeline_keeps_nodes_within_canvas_and_avoids_false_circles(self) -> None:
        config = PipelineConfig(input_path=Path("picture/orr_signature.png"), output_dir=Path("outputs/orr_signature"))
        artifacts = _run_pipeline_isolated(config)
        data = json.loads(artifacts.scene_graph_path.read_text(encoding="utf-8"))

        self.assertLess(len(data["nodes"]), 40)
        self.assertTrue(any((node.get("text_content") or "").strip() for node in data["nodes"] if node["type"] == "text"))
        for node in data["nodes"]:
            x1, y1, x2, y2 = node["bbox"]
            self.assertGreaterEqual(x1, 0)
            self.assertGreaterEqual(y1, 0)
            self.assertLessEqual(x2, data["width"])
            self.assertLessEqual(y2, data["height"])
            self.assertLessEqual(x1, x2)
            self.assertLessEqual(y1, y2)
        self.assertFalse(any(node.get("shape_hint") == "circle" for node in data["nodes"]))

    def test_visual_sample_pipeline_restores_colored_fill_and_transparency(self) -> None:
        config = PipelineConfig(
            input_path=Path("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png"),
            output_dir=Path("outputs/a22-visual"),
        )
        artifacts = _run_pipeline_isolated(config)
        svg_content = artifacts.final_svg_path.read_text(encoding="utf-8")

        fills = set(re.findall(r"fill='([^']+)'", svg_content))
        meaningful_fills = {
            fill
            for fill in fills
            if fill not in {"#000000", "#ffffff", "none"}
        }
        self.assertTrue(meaningful_fills)
        self.assertTrue("fill-opacity=" in svg_content or "opacity=" in svg_content)
        self.assertGreaterEqual(svg_content.count("<circle"), 10)

    def test_visual_sample_pipeline_preserves_large_ellipse_containers(self) -> None:
        config = PipelineConfig(
            input_path=Path("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png"),
            output_dir=Path("outputs/a22-structure"),
        )
        artifacts = _run_pipeline_isolated(config)
        svg_content = artifacts.final_svg_path.read_text(encoding="utf-8")
        graph_data = json.loads(artifacts.scene_graph_path.read_text(encoding="utf-8"))

        ellipse_regions = [
            obj for obj in graph_data["region_objects"]
            if obj.get("metadata", {}).get("shape_type") == "ellipse"
        ]
        self.assertGreaterEqual(len(ellipse_regions), 2)
        self.assertIn("<ellipse", svg_content)
        self.assertIn("data-shape-type='ellipse'", svg_content)

    def test_visual_sample_pipeline_detects_left_fan_structure(self) -> None:
        config = PipelineConfig(
            input_path=Path("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png"),
            output_dir=Path("outputs/a22-fan"),
        )
        artifacts = _run_pipeline_isolated(config)
        svg_content = artifacts.final_svg_path.read_text(encoding="utf-8")
        graph_data = json.loads(artifacts.scene_graph_path.read_text(encoding="utf-8"))

        self.assertIn("data-shape-type='fan'", svg_content)
        self.assertIn("data-relation-type='fan'", svg_content)
        self.assertTrue(any(relation["relation_type"] == "fan" for relation in graph_data["relations"]))

    def test_visual_sample_pipeline_promotes_connector_relations(self) -> None:
        config = PipelineConfig(
            input_path=Path("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png"),
            output_dir=Path("outputs/a22-connectors"),
        )
        artifacts = _run_pipeline_isolated(config)
        svg_content = artifacts.final_svg_path.read_text(encoding="utf-8")
        graph_data = json.loads(artifacts.scene_graph_path.read_text(encoding="utf-8"))

        relation_types = [relation["relation_type"] for relation in graph_data["relations"]]
        self.assertIn("connector", relation_types)
        self.assertGreaterEqual(len(graph_data["relations"]), 3)
        self.assertIn("data-relation-type='connector'", svg_content)

    def test_visual_sample_pipeline_builds_object_instances(self) -> None:
        config = PipelineConfig(
            input_path=Path("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png"),
            output_dir=Path("outputs/a22-objects"),
        )
        artifacts = _run_pipeline_isolated(config)
        graph_data = json.loads(artifacts.scene_graph_path.read_text(encoding="utf-8"))

        object_types = [obj["object_type"] for obj in graph_data["objects"]]
        self.assertIn("title", object_types)
        self.assertIn("network_container", object_types)
        self.assertTrue(any(any(node_id.startswith('region-') for node_id in obj['node_ids']) for obj in graph_data['objects'] if obj['object_type'] == 'network_container'))

    def test_visual_sample_pipeline_builds_object_driven_primitives(self) -> None:
        config = PipelineConfig(
            input_path=Path("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png"),
            output_dir=Path("outputs/a22-object-driven"),
        )
        artifacts = _run_pipeline_isolated(config)
        graph_data = json.loads(artifacts.scene_graph_path.read_text(encoding="utf-8"))
        svg_content = artifacts.final_svg_path.read_text(encoding="utf-8")

        self.assertTrue(graph_data["stroke_primitives"])
        self.assertTrue(graph_data["node_objects"])
        self.assertTrue(graph_data["region_objects"])
        self.assertTrue(graph_data["graph_edges"])
        self.assertIn("class='edge'", svg_content)
        self.assertIn("class='node'", svg_content)

    def test_run_pipeline_writes_round12_debug_artifacts(self) -> None:
        config = PipelineConfig(
            input_path=Path("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png"),
            output_dir=Path("outputs/a22-round12-debug"),
        )
        artifacts = _run_pipeline_isolated(config)

        self.assertTrue((config.output_dir / "debug_lines_mask.png").exists())
        self.assertTrue((config.output_dir / "debug_region_segmentation.png").exists())
        self.assertTrue((config.output_dir / 'debug_text_inpaint.png').exists())
        self.assertTrue((config.output_dir / 'debug_nodes_inpaint.png').exists())
        self.assertTrue((config.output_dir / 'debug_strokes_inpaint.png').exists())
        data = json.loads(artifacts.scene_graph_path.read_text(encoding="utf-8"))
        rect_like = [
            obj for obj in data["region_objects"]
            if (obj.get("outer_path") or "").count("L ") == 3
            and (obj.get("outer_path") or "").strip().endswith("Z")
        ]
        self.assertLessEqual(len(rect_like), 1)

    def test_proposals_for_stage_copies_stage_prefixed_masks(self) -> None:
        image = np.full((80, 120, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 20), (70, 55), (0, 0, 0), -1)
        config = PipelineConfig(input_path=Path('picture/F2.png'), output_dir=Path('outputs/test-stage-prefix'))

        proposals = _proposals_for_stage(image, config, config.output_dir, 'stage1')

        self.assertTrue(proposals)
        self.assertTrue(all(proposal.component_id.startswith('stage1-') for proposal in proposals))
        self.assertTrue(all(Path(proposal.mask_path).name.startswith('stage1-') for proposal in proposals))
        self.assertTrue(all((config.output_dir / proposal.mask_path).exists() for proposal in proposals))

    def test_inject_panel_background_regions_adds_layout_panels_from_text_columns(self) -> None:
        image = np.full((220, 400, 3), 255, dtype=np.uint8)
        colors = [(240, 240, 224), (232, 216, 232), (208, 224, 240), (216, 224, 216)]
        bounds = [(0, 98), (100, 198), (200, 298), (300, 399)]
        for (x1, x2), color in zip(bounds, colors):
            cv2.rectangle(image, (x1, 12), (x2, 208), color, -1)

        scene_graph = SceneGraph(
            width=400,
            height=220,
            nodes=[SceneNode(id='background-root', type='background', bbox=[0, 0, 400, 220], z_index=0, vector_mode='region_path', confidence=1.0)],
        )
        text_nodes = [
            SceneNode(id='text-1', type='text', bbox=[20, 24, 80, 46], z_index=1, vector_mode='text_box', confidence=0.9, text_content='Panel 1'),
            SceneNode(id='text-2', type='text', bbox=[120, 24, 180, 46], z_index=2, vector_mode='text_box', confidence=0.9, text_content='Panel 2'),
            SceneNode(id='text-3', type='text', bbox=[220, 24, 280, 46], z_index=3, vector_mode='text_box', confidence=0.9, text_content='Panel 3'),
            SceneNode(id='text-4', type='text', bbox=[320, 24, 380, 46], z_index=4, vector_mode='text_box', confidence=0.9, text_content='Panel 4'),
        ]

        updated = _inject_panel_background_regions(image, scene_graph, text_nodes)

        panel_nodes = [node for node in updated.nodes if node.id.startswith('panel-region-')]
        self.assertEqual(len(panel_nodes), 4)
        self.assertTrue(all(node.shape_hint == 'panel' for node in panel_nodes))
        self.assertTrue(all(node.type == 'region' for node in panel_nodes))
        self.assertTrue(all((node.fill or '').startswith('#') for node in panel_nodes))
        x_spans = sorted((node.bbox[0], node.bbox[2]) for node in panel_nodes)
        self.assertLessEqual(x_spans[0][0], 4)
        self.assertGreaterEqual(x_spans[-1][1], 396)


    def test_erase_region_nodes_whitens_detected_panel_area(self) -> None:
        image = np.full((40, 60, 3), 255, dtype=np.uint8)
        image[8:28, 10:40] = (180, 220, 240)
        image[14:18, 20:24] = (30, 60, 180)
        nodes = [
            SceneNode(id='panel-region-000', type='region', bbox=[10, 8, 40, 28], z_index=1, vector_mode='region_path', confidence=0.99, fill='#f0dcb4', shape_hint='panel')
        ]

        cleaned = _erase_region_nodes(image, nodes)

        self.assertTrue(np.array_equal(cleaned[12, 16], np.array([255, 255, 255], dtype=np.uint8)))
        self.assertTrue(np.array_equal(cleaned[16, 22], np.array([30, 60, 180], dtype=np.uint8)))
        self.assertTrue(np.array_equal(cleaned[35, 55], np.array([255, 255, 255], dtype=np.uint8)))

    def test_detect_panel_arrow_regions_uses_arrow_fill_and_marks_panel_arrow(self) -> None:
        image = np.full((320, 420, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 20), (180, 280), (240, 240, 224), -1)
        cv2.rectangle(image, (220, 20), (400, 280), (232, 216, 232), -1)
        arrow_color = (128, 48, 112)
        arrow_points = np.array([[150, 150], [220, 150], [255, 170], [220, 190], [150, 190]], dtype=np.int32)
        cv2.fillConvexPoly(image, arrow_points, arrow_color)

        panel_nodes = [
            SceneNode(id='panel-region-000', type='region', bbox=[20, 20, 180, 280], z_index=1, vector_mode='region_path', confidence=0.99, fill='#e0f0f0', shape_hint='panel'),
            SceneNode(id='panel-region-001', type='region', bbox=[220, 20, 400, 280], z_index=2, vector_mode='region_path', confidence=0.99, fill='#f0e0f0', shape_hint='panel'),
        ]

        arrow_nodes, arrow_objects = _detect_panel_arrow_regions(image, image.copy(), panel_nodes)

        self.assertTrue(arrow_nodes)
        self.assertTrue(arrow_objects)
        self.assertTrue(all(node.shape_hint == 'panel_arrow' for node in arrow_nodes))
        self.assertTrue(all(obj.metadata.get('shape_type') == 'panel_arrow_template' for obj in arrow_objects))
        self.assertEqual(arrow_nodes[0].fill, '#703080')
        self.assertEqual(arrow_objects[0].fill, '#703080')

    def test_filter_stroke_scene_graph_keeps_thin_strokes_only(self) -> None:
        scene_graph = SceneGraph(
            width=400,
            height=200,
            nodes=[
                SceneNode(id='stroke-thin', type='stroke', bbox=[20, 40, 220, 52], z_index=1, vector_mode='stroke_path', confidence=0.9),
                SceneNode(id='stroke-wide', type='stroke', bbox=[10, 20, 390, 160], z_index=2, vector_mode='stroke_path', confidence=0.9),
                SceneNode(id='text-1', type='text', bbox=[40, 80, 110, 100], z_index=3, vector_mode='text_box', confidence=0.9, text_content='Arrow'),
            ],
        )

        filtered = _filter_stroke_scene_graph(scene_graph)
        filtered_ids = {node.id for node in filtered.nodes}

        self.assertIn('stroke-thin', filtered_ids)
        self.assertNotIn('stroke-wide', filtered_ids)
        self.assertIn('text-1', filtered_ids)

    def test_should_inpaint_stroke_node_rejects_giant_stroke_cluster(self) -> None:
        scene_graph = SceneGraph(width=1400, height=760, nodes=[])
        giant_stroke = SceneNode(
            id='stage2-stroke-070',
            type='stroke',
            bbox=[12, 14, 1396, 757],
            z_index=1,
            vector_mode='stroke_path',
            confidence=0.7,
        )

        self.assertFalse(_should_inpaint_stroke_node(giant_stroke, scene_graph))




    def test_detect_container_detail_regions_extracts_internal_colored_components(self) -> None:
        image = np.full((120, 160, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 20), (140, 100), (240, 224, 240), -1)
        cv2.rectangle(image, (34, 40), (56, 62), (32, 64, 192), -1)
        cv2.rectangle(image, (92, 54), (122, 82), (48, 160, 80), -1)
        text_mask = np.zeros((120, 160), dtype=np.uint8)
        text_mask[24:34, 40:120] = 255

        scene_graph = SceneGraph(
            width=160,
            height=120,
            nodes=[
                SceneNode(
                    id='region-container-1',
                    type='region',
                    bbox=[20, 20, 140, 100],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    fill='#f0e0f0',
                    fill_opacity=0.4,
                    stroke='#f0e0f0',
                    group_id='component-text-overlay-001',
                    component_role='container_shape',
                    shape_hint='raster_candidate',
                ),
                SceneNode(id='text-1', type='text', bbox=[28, 24, 66, 32], z_index=2, vector_mode='text_box', confidence=0.9, text_content='Alpha'),
                SceneNode(id='text-2', type='text', bbox=[72, 24, 112, 32], z_index=3, vector_mode='text_box', confidence=0.9, text_content='Beta'),
                SceneNode(id='text-3', type='text', bbox=[30, 70, 62, 78], z_index=4, vector_mode='text_box', confidence=0.9, text_content='Gamma'),
                SceneNode(id='text-4', type='text', bbox=[88, 86, 126, 94], z_index=5, vector_mode='text_box', confidence=0.9, text_content='Delta'),
            ],
        )

        detail_nodes = _detect_container_detail_regions(image, scene_graph, text_mask)

        self.assertGreaterEqual(len(detail_nodes), 2)
        self.assertTrue(all(node.shape_hint == 'vector_candidate' for node in detail_nodes))
        self.assertTrue(any(node.fill == '#c04020' or node.fill == '#2040c0' for node in detail_nodes))
        self.assertTrue(any(node.fill == '#50a030' or node.fill == '#30a050' for node in detail_nodes))

    def test_build_region_vector_ignore_mask_preserves_panel_interior_regions(self) -> None:
        image = np.full((80, 120, 3), 255, dtype=np.uint8)
        image[:, :] = (224, 240, 240)
        image[20:60, 30:90] = (240, 224, 240)

        text_mask = np.zeros((80, 120), dtype=np.uint8)
        text_mask[28:34, 40:70] = 255
        node_mask = np.zeros((80, 120), dtype=np.uint8)
        node_mask[38:44, 50:80] = 255
        stroke_mask = np.zeros((80, 120), dtype=np.uint8)
        stroke_mask[48:50, 35:85] = 255
        panel_arrow_mask = np.zeros((80, 120), dtype=np.uint8)
        panel_arrow_mask[10:16, 92:110] = 255
        panel_mask = np.full((80, 120), 255, dtype=np.uint8)

        region_mask = _build_region_vector_ignore_mask(
            text_mask=text_mask,
            node_mask=node_mask,
            stroke_mask=stroke_mask,
            panel_arrow_mask=panel_arrow_mask,
        )
        healed = _heal_masked_stage_image(image, region_mask, kernel_size=7)
        fully_erased = _heal_masked_stage_image(image, cv2.bitwise_or(region_mask, panel_mask), kernel_size=7)

        self.assertTrue(np.array_equal(healed[24, 35], np.array([240, 224, 240], dtype=np.uint8)))
        self.assertTrue(np.array_equal(fully_erased[24, 35], np.array([255, 255, 255], dtype=np.uint8)))

    def test_prune_region_nodes_by_mask_drops_duplicate_region_covered_by_resolved_mask(self) -> None:
        ignore_mask = np.zeros((120, 160), dtype=np.uint8)
        ignore_mask[20:100, 20:140] = 255
        scene_graph = SceneGraph(
            width=160,
            height=120,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 160, 120], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='panel-region-000', type='region', bbox=[20, 20, 140, 100], z_index=1, vector_mode='region_path', confidence=0.99, fill='#ddeeff', shape_hint='panel'),
                SceneNode(id='region-duplicate', type='region', bbox=[22, 22, 138, 98], z_index=2, vector_mode='region_path', confidence=0.7),
                SceneNode(id='text-1', type='text', bbox=[40, 40, 100, 60], z_index=3, vector_mode='text_box', confidence=0.9, text_content='Panel'),
            ],
        )

        updated = _prune_region_nodes_by_mask(
            scene_graph,
            ignore_mask,
            artifacts_dir=None,
            protected_node_ids={'panel-region-000'},
        )

        remaining_ids = {node.id for node in updated.nodes}
        self.assertIn('panel-region-000', remaining_ids)
        self.assertIn('text-1', remaining_ids)
        self.assertNotIn('region-duplicate', remaining_ids)


    def test_filter_region_objects_drops_region_overlapping_text_bbox(self) -> None:
        scene_graph = SceneGraph(
            width=200,
            height=100,
            nodes=[
                SceneNode(id='region-text-box', type='region', bbox=[18, 18, 142, 62], z_index=1, vector_mode='region_path', confidence=0.8),
            ],
        )
        region_objects = [
            RegionObject(
                id='region-object-text-box',
                node_id='region-text-box',
                outer_path='M 18 18 L 142 18 L 142 62 L 18 62 Z',
                holes=[],
                fill='#000000',
                stroke='#000000',
                metadata={'entity_valid': True},
            )
        ]
        text_nodes = [
            SceneNode(id='text-1', type='text', bbox=[20, 20, 140, 60], z_index=2, vector_mode='text_box', confidence=0.95, text_content='Preprocessing and KG Integration')
        ]

        filtered = _filter_region_objects(scene_graph, region_objects, text_nodes)

        self.assertEqual(filtered, [])

    def test_filter_region_objects_keeps_large_raster_candidate_as_vector_region(self) -> None:
        scene_graph = SceneGraph(
            width=1440,
            height=760,
            nodes=[
                SceneNode(id='region-large', type='region', bbox=[177, 100, 700, 538], z_index=1, vector_mode='region_path', confidence=0.9, shape_hint='raster_candidate', fill='#f0e0f0'),
            ],
        )
        region_objects = [
            RegionObject(
                id='region-object-large',
                node_id='region-large',
                outer_path='M 177 100 L 700 100 L 700 538 L 177 538 Z',
                holes=[],
                fill='#f0e0f0',
                stroke='#f0e0f0',
                metadata={'entity_valid': True},
            )
        ]

        filtered = _filter_region_objects(scene_graph, region_objects, [])

        self.assertEqual(len(filtered), 1)

    def test_resolve_semantic_raster_objects_keeps_chart_like_regions_as_raster(self) -> None:
        image = np.full((180, 220, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 20), (180, 160), (230, 245, 230), -1)

        scene_graph = SceneGraph(
            width=220,
            height=180,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 220, 180], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-chart-1', type='region', bbox=[20, 20, 180, 160], z_index=1, vector_mode='region_path', confidence=0.9, shape_hint='raster_candidate'),
                SceneNode(id='text-1', type='text', bbox=[30, 40, 170, 65], z_index=2, vector_mode='text_box', confidence=0.9, text_content='Kaplan-Meier survival curves'),
            ],
        )
        raster_objects = [
            RasterObject(id='raster-region-chart-1', node_id='region-chart-1', bbox=[20, 20, 180, 160], image_href='data:image/png;base64,AAAA', metadata={'shape_hint': 'raster_candidate'})
        ]

        updated_graph, kept = _resolve_semantic_raster_objects(image, scene_graph, raster_objects)

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].metadata.get('semantic_label'), 'data_chart')
        chart_node = next(node for node in updated_graph.nodes if node.id == 'region-chart-1')
        self.assertEqual(chart_node.shape_hint, 'data_chart')

    def test_resolve_semantic_raster_objects_drops_nonchart_raster_fallback(self) -> None:
        image = np.full((220, 260, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 20), (220, 180), (232, 220, 244), -1)
        cv2.putText(image, 'Gene', (40, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2, cv2.LINE_AA)
        cv2.putText(image, 'Pathway', (120, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2, cv2.LINE_AA)

        scene_graph = SceneGraph(
            width=260,
            height=220,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 260, 220], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-diagram-1', type='region', bbox=[20, 20, 220, 180], z_index=1, vector_mode='region_path', confidence=0.9, shape_hint='raster_candidate'),
                SceneNode(id='text-1', type='text', bbox=[32, 48, 90, 74], z_index=2, vector_mode='text_box', confidence=0.9, text_content='Gene Pathway module'),
            ],
        )
        raster_objects = [
            RasterObject(id='raster-region-diagram-1', node_id='region-diagram-1', bbox=[20, 20, 220, 180], image_href='data:image/png;base64,AAAA', metadata={'shape_hint': 'raster_candidate'})
        ]

        updated_graph, kept = _resolve_semantic_raster_objects(image, scene_graph, raster_objects)

        self.assertEqual(kept, [])
        diagram_node = next(node for node in updated_graph.nodes if node.id == 'region-diagram-1')
        self.assertEqual(diagram_node.shape_hint, 'vector_candidate')


    def test_promote_svg_template_nodes_marks_clock_icon_before_raster_fallback(self) -> None:
        image = np.full((96, 96, 3), 255, dtype=np.uint8)
        cv2.circle(image, (48, 48), 28, (0, 0, 0), 3)
        cv2.line(image, (48, 48), (48, 28), (0, 0, 0), 3, cv2.LINE_AA)
        cv2.line(image, (48, 48), (62, 56), (0, 0, 0), 3, cv2.LINE_AA)
        scene_graph = SceneGraph(
            width=96,
            height=96,
            nodes=[
                SceneNode(
                    id='region-clock-1',
                    type='region',
                    bbox=[16, 16, 80, 80],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    fill='#d9e6f2',
                    shape_hint='raster_candidate',
                )
            ],
        )

        updated = _promote_svg_template_nodes(image, scene_graph)
        node = updated.nodes[0]

        self.assertEqual(node.shape_hint, 'svg_template')
        self.assertIn('svg_template:clock', node.component_role or '')
        raster_objects = _detect_raster_objects(image, image.copy(), updated, set())
        self.assertEqual(raster_objects, [])

    def test_promote_svg_template_nodes_uses_nearby_text_context_for_database_icon(self) -> None:
        image = np.full((180, 220, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (30, 30), (110, 110), (220, 235, 245), -1)
        cv2.rectangle(image, (45, 44), (95, 96), (120, 150, 180), 2)
        scene_graph = SceneGraph(
            width=220,
            height=180,
            nodes=[
                SceneNode(
                    id='region-db-1',
                    type='region',
                    bbox=[30, 30, 110, 110],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    fill='#d9e6f2',
                    shape_hint='raster_candidate',
                ),
                SceneNode(
                    id='text-db-1',
                    type='text',
                    bbox=[24, 116, 132, 138],
                    z_index=2,
                    vector_mode='text_box',
                    confidence=0.9,
                    text_content='Data Sources',
                ),
            ],
        )

        updated = _promote_svg_template_nodes(image, scene_graph, [scene_graph.nodes[1]])
        node = next(node for node in updated.nodes if node.id == 'region-db-1')

        self.assertEqual(node.shape_hint, 'svg_template')
        self.assertIn('svg_template:database', node.component_role or '')

    def test_promote_svg_template_nodes_does_not_promote_large_chart_panel_from_text_context(self) -> None:
        image = np.full((760, 1440, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (1181, 103), (1390, 633), (230, 240, 230), -1)
        scene_graph = SceneGraph(
            width=1440,
            height=760,
            nodes=[
                SceneNode(
                    id='region-metric-panel',
                    type='region',
                    bbox=[1181, 103, 1390, 633],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    fill='#e0f0e0',
                    shape_hint='raster_candidate',
                ),
                SceneNode(
                    id='text-metric-panel',
                    type='text',
                    bbox=[1200, 440, 1360, 470],
                    z_index=2,
                    vector_mode='text_box',
                    confidence=0.9,
                    text_content='Time-dependent AUC curves',
                ),
            ],
        )

        updated = _promote_svg_template_nodes(image, scene_graph, [scene_graph.nodes[1]])
        node = next(node for node in updated.nodes if node.id == 'region-metric-panel')

        self.assertEqual(node.shape_hint, 'vector_candidate')
        self.assertNotIn('svg_template:', node.component_role or '')

    def test_promote_svg_template_nodes_marks_tall_radial_icon_before_raster_fallback(self) -> None:
        image = np.full((429, 135, 3), 255, dtype=np.uint8)
        hub = (125, 211)
        for y in [20, 85, 140, 169, 196, 217, 246, 290, 309, 414]:
            cv2.circle(image, (24, y), 9, (170, 110, 50), -1)
            cv2.line(image, (33, y), hub, (70, 70, 70), 2, cv2.LINE_AA)
        scene_graph = SceneGraph(
            width=135,
            height=429,
            nodes=[
                SceneNode(
                    id='region-radial-1',
                    type='region',
                    bbox=[0, 0, 135, 429],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    fill='#ffffff',
                    shape_hint='raster_candidate',
                )
            ],
        )

        updated = _promote_svg_template_nodes(image, scene_graph)
        node = updated.nodes[0]

        self.assertEqual(node.shape_hint, 'svg_template')
        self.assertIn('svg_template:radial_icon', node.component_role or '')

    def test_resolve_semantic_raster_objects_promotes_radial_icon_and_drops_raster(self) -> None:
        image = np.full((429, 135, 3), 255, dtype=np.uint8)
        hub = (125, 211)
        for y in [20, 85, 140, 169, 196, 217, 246, 290, 309, 414]:
            cv2.circle(image, (24, y), 9, (170, 110, 50), -1)
            cv2.line(image, (33, y), hub, (70, 70, 70), 2, cv2.LINE_AA)

        scene_graph = SceneGraph(
            width=135,
            height=429,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 135, 429], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-radial-1', type='region', bbox=[0, 0, 135, 429], z_index=1, vector_mode='region_path', confidence=0.9, shape_hint='raster_candidate'),
            ],
        )
        raster_objects = [
            RasterObject(id='raster-radial', node_id='region-radial-1', bbox=[0, 0, 135, 429], image_href='data:image/png;base64,AAAA', metadata={'shape_hint': 'raster_candidate'})
        ]

        updated_graph, kept = _resolve_semantic_raster_objects(image, scene_graph, raster_objects)

        self.assertEqual(kept, [])
        node = next(node for node in updated_graph.nodes if node.id == 'region-radial-1')
        self.assertEqual(node.shape_hint, 'svg_template')
        self.assertIn('svg_template:radial_icon', node.component_role or '')



    def test_resolve_semantic_raster_objects_marks_promoted_region_as_semantic_recovered(self) -> None:
        image = np.full((220, 260, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 20), (220, 180), (232, 220, 244), -1)
        cv2.putText(image, 'Gene', (40, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2, cv2.LINE_AA)
        cv2.putText(image, 'Pathway', (120, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2, cv2.LINE_AA)

        scene_graph = SceneGraph(
            width=260,
            height=220,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 260, 220], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-diagram-1', type='region', bbox=[20, 20, 220, 180], z_index=1, vector_mode='region_path', confidence=0.9, shape_hint='raster_candidate'),
                SceneNode(id='text-1', type='text', bbox=[32, 48, 90, 74], z_index=2, vector_mode='text_box', confidence=0.9, text_content='Gene Pathway module'),
            ],
        )
        raster_objects = [
            RasterObject(id='raster-region-diagram-1', node_id='region-diagram-1', bbox=[20, 20, 220, 180], image_href='data:image/png;base64,AAAA', metadata={'shape_hint': 'raster_candidate'})
        ]

        updated_graph, kept = _resolve_semantic_raster_objects(image, scene_graph, raster_objects)

        self.assertEqual(kept, [])
        diagram_node = next(node for node in updated_graph.nodes if node.id == 'region-diagram-1')
        self.assertEqual(diagram_node.shape_hint, 'vector_candidate')
        self.assertIn('semantic_recovered', diagram_node.component_role or '')

    def test_resolve_semantic_raster_objects_preserves_existing_icon_objects(self) -> None:
        image = np.full((120, 120, 3), 255, dtype=np.uint8)
        scene_graph = SceneGraph(
            width=120,
            height=120,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 120, 120], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-chart-1', type='region', bbox=[20, 20, 90, 90], z_index=1, vector_mode='region_path', confidence=0.9, shape_hint='raster_candidate'),
                SceneNode(id='text-1', type='text', bbox=[18, 92, 94, 108], z_index=2, vector_mode='text_box', confidence=0.9, text_content='AUC chart'),
            ],
            icon_objects=[
                IconObject(
                    id='icon-1',
                    node_id='region-existing-icon',
                    bbox=[8, 8, 44, 44],
                    compound_path='M 8,8 L 44,8 L 44,44 L 8,44 Z',
                    fill='#111111',
                    fill_rule='evenodd',
                )
            ],
        )
        raster_objects = [
            RasterObject(id='raster-region-chart-1', node_id='region-chart-1', bbox=[20, 20, 90, 90], image_href='data:image/png;base64,AAAA', metadata={'shape_hint': 'raster_candidate'})
        ]

        updated_graph, kept = _resolve_semantic_raster_objects(image, scene_graph, raster_objects)

        self.assertEqual(len(kept), 1)
        self.assertEqual(len(updated_graph.icon_objects), 1)
        self.assertEqual(updated_graph.icon_objects[0].id, 'icon-1')

    def test_prune_region_nodes_by_mask_keeps_semantically_recovered_region(self) -> None:
        scene_graph = SceneGraph(
            width=320,
            height=200,
            nodes=[
                SceneNode(
                    id='region-semantic-main',
                    type='region',
                    bbox=[40, 30, 260, 170],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    fill='#f0e0f0',
                    component_role='semantic_recovered',
                    shape_hint='vector_candidate',
                ),
                SceneNode(id='text-1', type='text', bbox=[60, 40, 180, 68], z_index=2, vector_mode='text_box', confidence=0.95, text_content='Main body'),
            ],
        )
        ignore_mask = np.zeros((200, 320), dtype=np.uint8)
        ignore_mask[20:180, 30:270] = 255

        updated = _prune_region_nodes_by_mask(
            scene_graph,
            ignore_mask,
            artifacts_dir=None,
            protected_node_ids=set(),
        )

        remaining_ids = {node.id for node in updated.nodes}
        self.assertIn('region-semantic-main', remaining_ids)

    def test_detect_raster_objects_promotes_complex_icon_to_base64_image(self) -> None:
        image = np.full((80, 100, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (24, 20), (58, 52), (210, 240, 210), -1)
        cv2.circle(image, (32, 30), 5, (0, 0, 255), -1)
        cv2.rectangle(image, (42, 24), (52, 34), (255, 0, 0), -1)
        cv2.line(image, (28, 46), (54, 46), (0, 0, 0), 2, cv2.LINE_AA)

        scene_graph = SceneGraph(
            width=100,
            height=80,
            nodes=[
                SceneNode(
                    id='region-icon-1',
                    type='region',
                    bbox=[24, 20, 58, 52],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    shape_hint='raster_candidate',
                )
            ],
        )

        raster_objects = _detect_raster_objects(image, image.copy(), scene_graph, set())

        self.assertEqual(len(raster_objects), 1)
        self.assertTrue(raster_objects[0].image_href.startswith('data:image/png;base64,'))

    def test_inpaint_node_regions_uses_component_mask_not_bbox(self) -> None:
        output_dir = Path('outputs/test-node-mask-inpaint')
        masks_dir = output_dir / 'masks'
        masks_dir.mkdir(parents=True, exist_ok=True)

        image = np.full((30, 30, 3), 255, dtype=np.uint8)
        image[7:10, 7:10] = (0, 0, 255)
        cv2.circle(image, (15, 15), 3, (0, 0, 0), -1)

        local_mask = np.zeros((20, 20), dtype=np.uint8)
        cv2.circle(local_mask, (10, 10), 3, 255, -1)
        cv2.imwrite(str(masks_dir / 'node.png'), local_mask)

        scene_graph = SceneGraph(
            width=30,
            height=30,
            nodes=[
                SceneNode(
                    id='stage1-region-001',
                    type='region',
                    bbox=[5, 5, 25, 25],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    source_mask='masks/node.png',
                )
            ],
        )

        inpainted, _mask = _inpaint_node_and_icon_regions(
            image,
            scene_graph,
            {'stage1-region-001'},
            padding=0,
            artifacts_dir=output_dir,
        )

        self.assertTrue(np.array_equal(inpainted[8, 8], np.array([0, 0, 255], dtype=np.uint8)))

    def test_heal_masked_stage_image_closes_text_hole_without_inpainting(self) -> None:
        image = np.full((40, 40, 3), 255, dtype=np.uint8)
        image[8:32, 8:32] = (210, 235, 210)

        ignore_mask = np.zeros((40, 40), dtype=np.uint8)
        ignore_mask[17:23, 11:29] = 255

        healed = _heal_masked_stage_image(image, ignore_mask, kernel_size=7)

        self.assertTrue(np.array_equal(healed[19, 20], np.array([210, 235, 210], dtype=np.uint8)))
        self.assertTrue(np.array_equal(healed[4, 4], np.array([255, 255, 255], dtype=np.uint8)))




    def test_prune_region_nodes_by_mask_keeps_large_light_vector_candidate_region(self) -> None:
        scene_graph = SceneGraph(
            width=1408,
            height=768,
            nodes=[
                SceneNode(
                    id='region-main-body',
                    type='region',
                    bbox=[177, 100, 700, 538],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    fill='#f0e0f0',
                    stroke='#f0e0f0',
                    shape_hint='vector_candidate',
                ),
                SceneNode(id='text-1', type='text', bbox=[220, 120, 380, 150], z_index=2, vector_mode='text_box', confidence=0.95, text_content='Main panel body'),
            ],
        )
        ignore_mask = np.zeros((768, 1408), dtype=np.uint8)
        ignore_mask[110:530, 190:690] = 255

        updated = _prune_region_nodes_by_mask(
            scene_graph,
            ignore_mask,
            artifacts_dir=None,
            protected_node_ids=set(),
        )

        remaining_ids = {node.id for node in updated.nodes}
        self.assertIn('region-main-body', remaining_ids)

    def test_filter_region_objects_keeps_lightweight_container_overlapping_text_bbox(self) -> None:
        scene_graph = SceneGraph(
            width=240,
            height=140,
            nodes=[
                SceneNode(
                    id='region-light-container',
                    type='region',
                    bbox=[20, 20, 150, 68],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    fill='#f6f3ea',
                    stroke='#9aa3ad',
                    group_id='component-region-001',
                    component_role='container_shape',
                ),
            ],
        )
        region_objects = [
            RegionObject(
                id='region-object-light-container',
                node_id='region-light-container',
                outer_path='M 20 20 L 150 20 L 150 68 L 20 68 Z',
                holes=[],
                fill='#f6f3ea',
                stroke='#9aa3ad',
                metadata={'entity_valid': True, 'shape_type': 'rectangle'},
            )
        ]
        text_nodes = [
            SceneNode(id='text-1', type='text', bbox=[28, 30, 138, 54], z_index=2, vector_mode='text_box', confidence=0.95, text_content='Data Sources')
        ]

        filtered = _filter_region_objects(scene_graph, region_objects, text_nodes)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].id, 'region-object-light-container')

    def test_inject_network_container_object_preserves_icon_objects(self) -> None:
        scene_graph = SceneGraph(
            width=220,
            height=180,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 220, 180], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-main', type='region', bbox=[20, 20, 180, 150], z_index=1, vector_mode='region_path', confidence=0.9, fill='#f0f0f0'),
                SceneNode(id='stroke-1', type='stroke', bbox=[30, 40, 160, 60], z_index=2, vector_mode='stroke_path', confidence=0.9),
                SceneNode(id='text-1', type='text', bbox=[40, 70, 120, 90], z_index=3, vector_mode='text_box', confidence=0.95, text_content='Label'),
            ],
            icon_objects=[
                IconObject(
                    id='icon-keep',
                    node_id='region-icon',
                    bbox=[8, 8, 44, 44],
                    compound_path='M 8,8 L 44,8 L 44,44 L 8,44 Z',
                    fill='#111111',
                    fill_rule='evenodd',
                )
            ],
        )

        updated = _inject_network_container_object(scene_graph)

        self.assertEqual(len(updated.icon_objects), 1)
        self.assertEqual(updated.icon_objects[0].id, 'icon-keep')


if __name__ == "__main__":
    unittest.main()

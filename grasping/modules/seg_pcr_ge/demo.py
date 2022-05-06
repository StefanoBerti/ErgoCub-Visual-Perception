import pycuda.autoinit

import torch
import numpy as np
from open3d.cpu.pybind.camera import PinholeCameraParameters
from sklearn.cluster import DBSCAN

from denoising.src.denoiser import Denoising
from ransac.utils.inference import Runner
from shape_reconstruction.tensorrt.utils.inference import Infer as InferPcr

a = torch.zeros([1]).to('cuda')
print('Loading Shape Reconstruction engine')
backbone = InferPcr('./shape_reconstruction/tensorrt/assets/pcr.engine')
print('Shape Reconstruction engine loaded')

from segmentation.tensorrt.utils.inference import Infer as InferSeg

print('Loading segmentation engine')
model = InferSeg('./segmentation/tensorrt/assets/seg_int8.engine')
print('Segmentation engine loaded')

from seg_pcr_ge.delete import GraspEstimator
# from ransac.utils.grasp_estimator import GraspEstimator

# print('Loading RANSAC engine')
ransac = Runner('./ransac/assets/ransac_5000.engine')
# print('RANSAC engine loaded')

from shape_reconstruction.tensorrt.utils.decoder import Decoder

decoder = Decoder()

import copy

import cv2
from open3d.cpu.pybind.geometry import PointCloud, TriangleMesh
from open3d.cpu.pybind.utility import Vector3dVector, set_verbosity_level
from open3d.cpu.pybind.visualization import Visualizer, draw_geometries

from utils.input import RealSense
from utils.timer import Timer
from utils.misc import draw_mask

i = 0

grasp_estimator = GraspEstimator(ransac)
denoising = Denoising()
def inference(rgb, depth):

    mask = model(rgb)
    mask = cv2.resize(mask, dsize=(640, 480), interpolation=cv2.INTER_NEAREST)

    segmented_depth = copy.deepcopy(depth)
    segmented_depth[mask != 1] = 0

    # Adjust size
    distance = segmented_depth[segmented_depth != 0].mean()
    if len(segmented_depth.nonzero()[0]) >= 4096:
        segmented_pc = RealSense.depth_pointcloud(segmented_depth)

        with Timer(name='downsample'):
            # Downsample
            idx = np.random.choice(segmented_pc.shape[0], 4096, replace=False)
            downsampled_pc = segmented_pc[idx]
            #
            # global i
            # np.save(f'pc_noise{i}', downsampled_pc)
            # i += 1
            # if i == 10:
            #     exit()

        with Timer(name='denoise'):
            # Denoise
            # clustering = DBSCAN(eps=0.05, min_samples=10).fit(downsampled_pc)  # 0.1 10 are perfect but slow
            # close = clustering.labels_[downsampled_pc.argmax(axis=0)[2]]
            # denoised_pc = downsampled_pc[clustering.labels_ == close]

            denoised_pc = denoising(downsampled_pc)

        # denoised_pc = downsampled_pc
        with Timer(name='adjust'):
            if denoised_pc.shape[0] > 2024:
                idx = np.random.choice(denoised_pc.shape[0], 2024, replace=False)
                size_pc = denoised_pc[idx]
            else:
                print('Info: Partial Point Cloud padded')
                diff = 2024 - denoised_pc.shape[0]
                pad = np.zeros([diff, 3])
                pad[:] = segmented_pc[0]
                size_pc = np.vstack((denoised_pc, pad))

        with Timer(name='normalize'):
            # Normalize
            mean = np.mean(size_pc, axis=0)
            var = np.sqrt(np.max(np.sum((size_pc - mean) ** 2, axis=1)))
            normalized_pc = (size_pc - mean) / (var * 2)
            normalized_pc[..., -1] = -normalized_pc[..., -1]

        with Timer(name='backbone'):
            # Reconstruction
            fast_weights = backbone(normalized_pc)

            # global i
            # np.save(f'test{i}', normalized_pc)
            # i += 1
            # if i == 10:
            #     exit()

        with Timer(name='implicit function'):
            res = decoder(fast_weights)
            print(res.shape[0])

        if res.shape[0] < 10_000:
            poses = grasp_estimator.find_poses(res * np.array([1, 1, -1]), 0.001, 5000)
            # poses = None
            if poses is not None:
                poses[0] = (poses[0] * (var * 2) + mean)
                poses[2] = (poses[2] * (var * 2) + mean)
        else:
            print('Warning: corrupted results. Probable cause: too much input noise')
            poses = None
            mean = 0
            var = 1
            res = np.array([[0, 0, 0]])
            size_pc = np.array([[0, 0, 0]])
    else:
        print('Warning: not enough input points. Skipping reconstruction')
        poses = None
        mean = 0
        var = 1
        res = np.array([[0, 0, 0]])
        size_pc = np.array([[0, 0, 0]])

    return {'mask': mask, 'partial': size_pc, 'reconstruction': (res * np.array([1, 1, -1]) * (var * 2) + mean),
            'grasp_poses': poses, 'distance': distance}


class Config:
    class Debug:
        video_feed = True
        o3d_viz = True

        class O3D:
            point_clouds = False
            grasping_points = True


def main():
    camera = RealSense()

    if Config.Debug.o3d_viz:
        vis = Visualizer()
        vis2 = Visualizer()
        vis.create_window('Pose Estimation')
        vis2.create_window()

        camera_parameters = PinholeCameraParameters()
        camera_parameters.extrinsic = np.array([[0, 0, 1, 0],
                                                [0, 1, 0, 0],
                                                [-1, 0, 0, 0.5],
                                                [0, 0, 0, 1]])

        intrinsics = {'fx': 1000, 'fy': 1000, 'cx': 959.5,
                      'cy': 539.5,
                      'width': 1920, 'height': 1080}

        camera_parameters.intrinsic.set_intrinsics(**intrinsics)

        control = vis.get_view_control()
        control.convert_from_pinhole_camera_parameters(camera_parameters)
        control = vis2.get_view_control()
        control.convert_from_pinhole_camera_parameters(camera_parameters)

        scene_pcd = PointCloud()
        part_pcd = PointCloud()
        pred_pcd = PointCloud()
        coords_mesh = [TriangleMesh.create_coordinate_frame(size=0.1) for _ in range(2)]

        render_setup = False

    while True:
        rgb, depth = camera.read()
        rgb = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)
        outputs = inference(rgb, depth)
        mask, partial, reconstruction, poses, distance = \
            outputs['mask'], outputs['partial'], outputs['reconstruction'], outputs['grasp_poses'], outputs['distance']

        # Visualization
        if Config.Debug.video_feed:
            res1, res2 = draw_mask(rgb, mask)

            font = cv2.FONT_ITALIC
            bottomLeftCornerOfText = (10, 30)
            fontScale = 1
            fontColor = (255, 255, 255)
            thickness = 1
            lineType = 2

            cv2.putText(res2, f'Distance: {distance / 1000}',
                        bottomLeftCornerOfText,
                        font,
                        fontScale,
                        fontColor,
                        thickness,
                        lineType)

            # cv2.imshow('Segmentation 1', cv2.cvtColor(res1, cv2.COLOR_RGB2BGR))
            # cv2.imshow('Segmentation 2', cv2.cvtColor(res2, cv2.COLOR_RGB2BGR))
            cv2.imshow('Segmentation 1', res1)
            cv2.imshow('Segmentation 2', res2)

            cv2.waitKey(1)

        if Config.Debug.o3d_viz:
            if poses is not None:
                best_centers = (poses[0], poses[2])
                best_rots = (poses[1], poses[3])
                size = 0.1
            else:
                best_centers = (np.zeros([3]), np.zeros([3]))
                best_rots = (np.zeros([3, 3]), np.zeros([3, 3]))
                size = 0.01


            # Orient poses
            for c, R, coord_mesh in zip(best_centers, best_rots, coords_mesh):
                coord_mesh_ = TriangleMesh.create_coordinate_frame(size=size, origin=[0, 0, 0])\
                    .rotate(R, center=[0, 0, 0]).translate(c, relative=False)

                # Update mesh
                coord_mesh.triangles = coord_mesh_.triangles
                coord_mesh.vertices = coord_mesh_.vertices

            scene_pc = RealSense.rgb_pointcloud(depth, rgb)

            part_pc = PointCloud()
            part_pc.points = Vector3dVector(partial) #  + [0, 0, 1]
            part_pc.paint_uniform_color([0, 1, 0])
            pred_pc = PointCloud()
            pred_pc.points = Vector3dVector(reconstruction)
            pred_pc.paint_uniform_color([1, 0, 0])

            scene_pcd.clear()
            part_pcd.clear()
            pred_pcd.clear()

            scene_pcd += scene_pc
            part_pcd += part_pc
            pred_pcd += pred_pc

            if not render_setup:
                vis2.add_geometry(scene_pcd)
                vis.add_geometry(part_pcd)
                vis.add_geometry(pred_pcd)
                for pose in coords_mesh:
                    vis.add_geometry(pose)

                render_setup = True

            vis2.update_geometry(scene_pcd)
            vis.update_geometry(part_pcd)
            vis.update_geometry(pred_pcd)
            for pose in coords_mesh:
                vis2.update_geometry(pose)

            vis.poll_events()
            vis.update_renderer()
            vis2.poll_events()
            vis2.update_renderer()


import os, sys

class shush:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout


if __name__ == '__main__':
    main()

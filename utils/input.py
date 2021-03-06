import cv2
import numpy as np
import pyrealsense2 as rs


# YCB
# intrinsics = {'fx': 384.025146484375, 'fy': 384.025146484375, 'ppx': 319.09661865234375, 'ppy': 237.75723266601562,
#               'width': 640, 'height': 480}
# Realsense D435i rgb
# intrinsics = {'fx': 612.7910766601562, 'fy': 611.8779296875, 'ppx': 321.7364196777344, 'ppy': 245.0658416748047,
#               'width': 640, 'height': 480}


class RealSense:
    """" rgb_res = (width, height)"""
    def __init__(self, rgb_res=(640, 480), depth_res=(640, 480), fps=60,
                 depth_format=rs.format.z16,
                 color_format=rs.format.bgr8, from_file=None):
        self.pipeline = rs.pipeline()
        configs = {}
        configs['device'] = 'Intel RealSense D435i'

        config = rs.config()

        if from_file:
            rs.config.enable_device_from_file(config, from_file)

        config.enable_stream(rs.stream.depth, *rgb_res, depth_format, fps)
        config.enable_stream(rs.stream.color, *depth_res, color_format, fps)
        self.profile = self.pipeline.start(config)

        configs['depth'] = {'width': depth_res[0], 'height': depth_res[1], 'format': 'z16', 'fps': fps}
        configs['color'] = {'width': depth_res[0], 'height': depth_res[1], 'format': 'rgb8', 'fps': fps}


        HIGH_ACCURACY = 3
        HIGH_DENSITY = 4
        MEDIUM_DENSITY = 5
        if not from_file:
            self.profile.get_device().sensors[0].set_option(rs.option.visual_preset, HIGH_DENSITY)

        # sensors = self.profile.get_device().query_sensors()
        # for sensor in sensors:
        #     if sensor.supports(rs.option.auto_exposure_priority):
        #         exp = sensor.set_option(rs.option.auto_exposure_priority, 0)
        #         exp = sensor.get_option(rs.option.auto_exposure_priority)

        configs['options'] = {}
        for device in self.profile.get_device().sensors:
            configs['options'][device.name] = {}
            for option in device.get_supported_options():
                configs['options'][device.name][str(option)[7:]] = str(device.get_option(option))

        self.configs = configs
        self.align = rs.align(rs.stream.color)

    def intrinsics(self):
        return self.profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()

    def read(self):
        frames = self.pipeline.wait_for_frames(100)
        aligned_frames = self.align.process(frames)

        depth_frame = aligned_frames.get_depth_frame()  # aligned_depth_frame is a 640x480 depth image
        color_frame = aligned_frames.get_color_frame()
        # depth_frame = frames.get_depth_frame()  # aligned_depth_frame is a 640x480 depth image
        # color_frame = frames.get_color_frame()

        depth_image = np.asanyarray(depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())

        return color_image, depth_image

    @classmethod
    def rgb_pointcloud(cls, depth_image, rgb_image, intrinsics=None):
        import open3d as o3d
        depth_image = o3d.geometry.Image(depth_image)
        rgb_image = o3d.geometry.Image(rgb_image)
        rgbd = o3d.geometry.RGBDImage().create_from_color_and_depth(rgb_image, depth_image,
                                                                    convert_rgb_to_intensity=False,
                                                                    depth_scale=1000)

        if intrinsics is None:
            intrinsics = {'fx': 612.7910766601562, 'fy': 611.8779296875, 'ppx': 321.7364196777344,
                          'ppy': 245.0658416748047, 'width': 640, 'height': 480}

        camera = o3d.camera.PinholeCameraIntrinsic(intrinsics['width'], intrinsics['height'], intrinsics['fx'],
                                                   intrinsics['fy'], intrinsics['ppx'], intrinsics['ppy'])

        pcd = o3d.geometry.PointCloud.create_from_rgbd_image(rgbd, camera)
        pcd.transform([[1, 0, 0, 0],
                       [0, -1, 0, 0],
                       [0, 0, -1, 0],
                       [0, 0, 0, 1]])

        return pcd

    @classmethod
    def depth_pointcloud(cls, depth_image, intrinsics=None):
        import open3d as o3d
        depth_image = o3d.geometry.Image(depth_image)

        if intrinsics is None:
            intrinsics = {'fx': 612.7910766601562, 'fy': 611.8779296875, 'ppx': 321.7364196777344,
                          'ppy': 245.0658416748047, 'width': 640, 'height': 480}

        camera = o3d.camera.PinholeCameraIntrinsic(intrinsics['width'], intrinsics['height'], intrinsics['fx'],
                                                   intrinsics['fy'], intrinsics['ppx'], intrinsics['ppy'])

        pcd = o3d.geometry.PointCloud.create_from_depth_image(depth_image, camera)
        pcd.transform([[1, 0, 0, 0],
                       [0, -1, 0, 0],
                       [0, 0, -1, 0],
                       [0, 0, 0, 1]])

        return np.array(pcd.points)

    def stop(self):
        self.pipeline.stop()


def test_fps():
    import tqdm
    camera = RealSense()

    for _ in tqdm.tqdm(range(1000)):
        rgb, depth = camera.read()
        cv2.waitKey(1)

if __name__ == '__main__':
    test_fps()
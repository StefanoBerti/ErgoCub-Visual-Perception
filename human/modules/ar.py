import pickle
import numpy as np
from human.utils.params import TRXConfig
from utils.runner import Runner
from tqdm import tqdm


class ActionRecognizer:
    def __init__(self, args):
        self.device = args.device

        self.ar = Runner(args.trt_path)

        self.support_set = np.zeros((args.way, args.seq_len, args.n_joints * 3), dtype=float)
        self.previous_frames = []
        self.support_labels = []
        self.seq_len = args.seq_len
        self.way = args.way
        self.n_joints = args.n_joints

        self.requires_focus = [False for _ in range(args.way)]

    def inference(self, pose):
        if pose is None:
            return {}

        if len(self.support_labels) == 0:  # no class to predict
            return {}

        pose = pose.reshape(-1)

        self.previous_frames.append(pose)
        if len(self.previous_frames) < self.seq_len:  # few samples
            return {}
        elif len(self.previous_frames) == self.seq_len + 1:
            self.previous_frames = self.previous_frames[1:]  # add as last frame

        # Predict actual action
        poses = np.stack(self.previous_frames).reshape(self.seq_len, -1).astype(np.float32)
        labels = np.array(list(range(self.way)))
        ss = self.support_set.reshape(-1, 90).astype(np.float32)
        outputs = self.ar([ss, labels, poses])
        outputs = outputs[0].reshape(1, 5)

        # Softmax
        max_along_axis = outputs.max(axis=1, keepdims=True)
        exponential = np.exp(outputs - max_along_axis)
        denominator = np.sum(exponential, axis=1, keepdims=True)
        predicted = exponential / denominator
        predicted = predicted[0]

        results = {}  # return output as dictionary
        predicted = predicted[:len(self.support_labels)]
        for k in range(len(predicted)):
            if k < len(self.support_labels):
                results[self.support_labels[k]] = (predicted[k], self.requires_focus[k])
            else:
                results['Action_{}'.format(k)] = (predicted[k], self.requires_focus[k])
        return results

    def remove(self, flag):
        """
        flag: Str
        """
        index = self.support_labels.index(flag)
        self.support_labels.remove(flag)
        self.support_set[index] = np.zeros_like(self.support_set[index])
        self.requires_focus[index] = False

    def debug(self):
        with open('assets/skeleton_types.pkl', "rb") as inp:
            sk = pickle.load(inp)
        ed = sk['smpl+head_30']['edges']
        for i in range(len(self.support_set)):
            label = 'None' if i >= len(self.support_labels) else self.support_labels[i]
            yield self.support_set[i], label, ed

    def train(self, raw):
        """
        raw: Tuple ( FloatTensor Nx30x3, Str)
        """
        if raw is not None:  # if some data are given
            # Convert raw
            x = raw[0].reshape(self.seq_len, -1)
            if raw[1] not in self.support_labels and len(self.support_labels) < 5:
                self.support_labels.append(raw[1])
            y = np.array([int(self.support_labels.index(raw[1]))])
            self.support_set[y.item()] = x
            self.requires_focus[y.item()] = raw[2]


if __name__ == "__main__":
    ar = ActionRecognizer(TRXConfig())
    for _ in range(5):
        ar.train((np.random.random((16, 30, 3)), "test", True))
    for _ in tqdm(range(100000)):
        ar.inference(np.random.random((30, 3)))

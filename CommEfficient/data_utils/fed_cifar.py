import json
import os

import numpy as np

from data_utils import FedDataset, fetch_mal_data
import torchvision
from torchvision.datasets import CIFAR10, CIFAR100
from PIL import Image

__all__ = ["FedCIFAR10", "FedCIFAR100"]

class FedCIFAR10(FedDataset):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # hardcoded for now
        #self.data_ownership = False
        self.data_ownership = True
        client_datasets = []
        self.num_classes = 10

        # keep all data in memory
        if self.type == "train":
            for client_id in range(len(self.images_per_client)):
                client_datasets.append(np.load(self.client_fn(client_id)))
            self.client_datasets = client_datasets
        elif self.type == "val":
            with np.load(self.test_fn()) as test_set:
                self.test_images = test_set["test_images"]
                self.test_targets = test_set["test_targets"]

        if self.is_malicious_train or self.is_malicious_val:
            np.random.seed(42)
            if self.data_ownership:
                print("Using training data")
                if not client_datasets:
                    for client_id in range(len(self.images_per_client)):
                        client_datasets.append(np.load(self.client_fn(client_id)))
                client_datasets = [item for sublist in client_datasets for item in sublist]
                test_images = client_datasets
                test_targets = np.load(self.train_targets_fn())
            else:
                with np.load(self.test_fn()) as test_set:
                    test_images = test_set["test_images"]
                    test_targets = test_set["test_targets"]
            mal_data, mal_labels = fetch_mal_data(test_images, test_targets, self.args, self.num_classes, self.images_per_client)
            print(f"Target class: {mal_labels} of {len(mal_data)}")
            self.mal_images = mal_data
            self.mal_targets = mal_labels
            self.test_images = self.mal_images
            self.test_targets = self.mal_targets

    def fetch_test_data(self, test_images, test_targets, allowed_source_labels):
        true_images = []
        true_labels = []
        for i, test_label in enumerate(test_targets):
            if len(allowed_source_labels) == 0:
                break
            if test_label in allowed_source_labels:
                allowed_source_labels.remove(test_label)
                true_images.append(test_images[i])
                true_labels.append(test_label)
        return np.array(true_images), np.array(true_labels)

    def fetch_source_idxs(self, test_images, args):
        if args.mal_type in ["A", "B"]:
            return list(np.random.choice(self.num_classes, size=self.num_mal_images * 10))
        elif args.mal_type in ["C", "D"]:
            return [7 for _ in range(self.num_mal_images * 10)]

    def fetch_targets(self, images_per_client, args):
        if args.mal_type in ["A", "C"]:
            return np.array(list(range(len(self.images_per_client))))
        elif args.mal_type in ["B", "D"]:
            return np.array([1])

    def prepare_datasets(self, download=True):
        os.makedirs(self.dataset_dir, exist_ok=True)
        dataset = torchvision.datasets.__dict__.get(self.dataset_name)
        vanilla_train = dataset(self.dataset_dir,
                                train=True,
                                download=download)
        vanilla_test = dataset(self.dataset_dir,
                               train=False,
                               download=download)

        train_images = vanilla_train.data
        train_targets = np.array(vanilla_train.targets)
        classes = vanilla_train.classes

        test_images = vanilla_test.data
        test_targets = np.array(vanilla_test.targets)

        images_per_client = []

        # split train_images/targets into client datasets, save to disk
        for client_id in range(len(classes)):
            cur_client = np.where(train_targets == client_id)[0]
            client_images = train_images[cur_client]
            client_targets = train_targets[cur_client]

            images_per_client.append(len(client_targets))

            fn = self.client_fn(client_id)
            if os.path.exists(fn):
                raise RuntimeError("won't overwrite existing split")
            np.save(fn, client_images)

        # save test set to disk
        fn = self.test_fn()
        if os.path.exists(fn):
            raise RuntimeError("won't overwrite exiting test set")
        np.savez(fn,
                 test_images=test_images,
                 test_targets=test_targets)

        fn = self.train_targets_fn()
        if os.path.exists(fn):
            raise RuntimeError("won't overwrite exiting test set")
        np.save(fn, train_targets)

        # save global stats to disk
        fn = self.stats_fn()
        if os.path.exists(fn):
            raise RuntimeError("won't overwrite existing stats file")
        stats = {"images_per_client": images_per_client,
                 "num_val_images": len(test_targets)}
        with open(fn, "w") as f:
            json.dump(stats, f)

    def _get_train_item(self, client_id, idx_within_client):
        client_dataset = self.client_datasets[client_id]
        raw_image = client_dataset[idx_within_client]
        target = client_id

        image = Image.fromarray(raw_image)

        return image, target

    def _get_val_item(self, idx):
        idx = idx % len(self.test_images)
        raw_image = self.test_images[idx]
        image = Image.fromarray(raw_image)
        return image, self.test_targets[idx]

    """
    def _get_mal_item(self, idx):
        raw_image = self.mal_images[idx]
        image = Image.fromarray(raw_image)
        return image, self.mal_targets[idx]
    """
    def _get_mal_item(self, idx_within_client):
        print(f"fetching {idx_within_client}")
        new_idx = idx_within_client % len(self.mal_images)
        raw_image = self.mal_images[new_idx]
        image = Image.fromarray(raw_image)
        return image, self.mal_targets[new_idx]

    def _get_mal_item(self):
        new_idx = np.random.choice(len(self.mal_images))
        raw_image = self.mal_images[new_idx]
        image = Image.fromarray(raw_image)
        return image, self.mal_targets[new_idx]

    def client_fn(self, client_id):
        fn = "client{}.npy".format(client_id)
        return os.path.join(self.dataset_dir, fn)

    def test_fn(self):
        return os.path.join(self.dataset_dir, "test.npz")

    def train_targets_fn(self):
        return os.path.join(self.dataset_dir, "train_targets.npy")

class FedCIFAR100(FedCIFAR10):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

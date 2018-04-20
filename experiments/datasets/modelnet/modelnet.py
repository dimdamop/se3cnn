# pylint: disable=E1101,R,C
import glob
import os
import numpy as np
import torch
import torch.utils.data
import subprocess

"""
typical usage

https://github.com/antigol/obj2voxel is needed

cache = CacheNPY("v64", repeat=24, transform=Obj2Voxel(64))

def transform(x):
    x = cache(x)
    return torch.from_numpy(x.astype(np.float32)).unsqueeze(0)

def target_transform(x):
    classes = ["bathtub", "bed", "chair", "desk", "dresser", "monitor", "night_stand", "sofa", "table", "toilet"]
    return classes.index(x)

dataset = ModelNet10("./modelnet10/", download=True, transform=transform, target_transform=target_transform)
"""

class Obj2Voxel:
    def __init__(self, size, rotate=True, tmpfile="tmp.npy"):
        self.size = size
        self.rotate = rotate
        self.tmpfile = tmpfile

    def __call__(self, file_path):
        command = ["obj2voxel", "--size", str(self.size), file_path, self.tmpfile]
        if self.rotate:
            command += ["--rotate"]
        subprocess.run(command)
        return np.load(self.tmpfile).astype(np.int8).reshape((self.size, self.size, self.size))


class CacheNPY:
    def __init__(self, prefix, repeat, transform, pick_randomly=True):
        self.transform = transform
        self.prefix = prefix
        self.repeat = repeat
        self.pick_randomly = pick_randomly

    def check_trans(self, file_path):
        print("transform {}...".format(file_path))
        try:
            return self.transform(file_path)
        except:
            print("Exception during transform of {}".format(file_path))
            raise

    def __call__(self, file_path):
        head, tail = os.path.split(file_path)
        root, _ = os.path.splitext(tail)
        npy_path = os.path.join(head, self.prefix + root + '_{0}.npy')

        exists = [os.path.exists(npy_path.format(i)) for i in range(self.repeat)]

        if self.pick_randomly and all(exists):
            i = np.random.randint(self.repeat)
            try:
                return np.load(npy_path.format(i))
            except OSError:
                exists[i] = False

        if self.pick_randomly:
            img = self.check_trans(file_path)
            np.save(npy_path.format(exists.index(False)), img)

            return img

        output = []
        for i in range(self.repeat):
            try:
                img = np.load(npy_path.format(i))
            except (OSError, FileNotFoundError):
                img = self.check_trans(file_path)
                np.save(npy_path.format(i), img)
            output.append(img)

        return output

    def __repr__(self):
        return self.__class__.__name__ + '(prefix={0}, transform={1})'.format(self.prefix, self.transform)


class ModelNet10(torch.utils.data.Dataset):
    '''
    Download ModelNet and output valid obj files content
    '''

    url_data = 'http://vision.princeton.edu/projects/2014/3DShapeNets/ModelNet10.zip'
    # url_data40 = 'http://modelnet.cs.princeton.edu/ModelNet40.zip'

    def __init__(self, root, train=True, download=False, transform=None, target_transform=None):
        self.root = os.path.expanduser(root)

        self.transform = transform
        self.target_transform = target_transform

        if download:
            self.download()

        if not self._check_exists():
            raise RuntimeError('Dataset not found.' +
                               ' You can use download=True to download it')

        self.files = sorted(glob.glob(os.path.join(self.root, "ModelNet10", "*", "train" if train else "test", "*.obj")))

    def __getitem__(self, index):
        img = self.files[index]
        target = img.split(os.path.sep)[-3]

        if self.transform is not None:
            img = self.transform(img)

        if self.target_transform is not None:
            target = self.target_transform(target)

        return img, target

    def __len__(self):
        return len(self.files)

    def _check_exists(self):
        files = glob.glob(os.path.join(self.root, "ModelNet10", "*", "*", "*.obj"))

        return len(files) > 0

    def _download(self, url):
        import requests

        filename = url.split('/')[-1]
        file_path = os.path.join(self.root, filename)

        if os.path.exists(file_path):
            return file_path

        print('Downloading ' + url)

        r = requests.get(url, stream=True)
        with open(file_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=16 * 1024 ** 2):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    f.flush()

        return file_path

    def _unzip(self, file_path):
        import zipfile

        if os.path.exists(os.path.join(self.root, "ModelNet10")):
            return

        print('Unzip ' + file_path)

        zip_ref = zipfile.ZipFile(file_path, 'r')
        zip_ref.extractall(self.root)
        zip_ref.close()
        os.unlink(file_path)

    def _off2obj(self):
        print('Convert OFF into OBJ')

        files = glob.glob(os.path.join(self.root, "ModelNet10", "*", "*", "*.off"))
        for file_name in files:
            with open(file_name, "rt") as fi:
                data = fi.read().split("\n")

            assert data[0] == "OFF"
            n, m, _ = [int(x) for x in data[1].split()]
            vertices = data[2: 2 + n]
            faces = [x.split()[1:] for x in data[2 + n: 2 + n + m]]
            result = "o object\n"
            for v in vertices:
                result += "v " + v + "\n"

            for f in faces:
                result += "f " + " ".join(str(int(x) + 1) for x in f) + "\n"

            with open(file_name.replace(".off", ".obj"), "wt") as fi:
                fi.write(result)

    def download(self):

        if self._check_exists():
            return

        # download files
        try:
            os.makedirs(self.root)
        except OSError as e:
            if e.errno == os.errno.EEXIST:
                pass
            else:
                raise

        file_path = self._download(self.url_data)
        self._unzip(file_path)
        self._off2obj()

        print('Done!')

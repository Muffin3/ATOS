import math
import hashlib
import exeptions
from user import User
from termcolor import colored
from superblock import SuperBlock
from file import File


class Atos:

    def __init__(self, os_path):
        self.super_block = SuperBlock(os_path)
        self.location = ''
        self.rwx, self.current_dir = self.get_directory(self.location)
        self.users = self.load_users()
        self.user = None

    @property
    def location(self):
        return self.__location

    @location.setter
    def location(self, location):
        self.__location = location

    """System calls"""

    def make_file(self, path, mod='0110100', uid=1, data='', attr='000'):
        """Make a new file"""
        full_path = self.path_conversion(path)   # built full path
        pos = full_path.rfind('/')
        full_path, full_name = full_path[:pos], full_path[pos+1:]    # divide path and name
        name, ext = self.parse_ext(full_name)   # parse extension
        rwx, directory = self.get_directory(full_path)    # get target directory
        if self.read_directory(directory).get(full_name):  # check existed files
            raise exeptions.FileExists(full_name)
        count = self.get_cluster_count(data) if data else 1  # get required cluster's count
        clusters = self.get_free_clusters(count)    # get numbers of free clusters
        self.write_record(File(name, ext, mod, clusters[0], self.user.id, data, attr), directory)
        self.set_cluster_engaged(clusters)
        if data:
            self.write_data(clusters, data)

    def remove_file(self, path):
        pass

    def change_directory(self, path):
        path = self.path_conversion(path)
        rwx, directory = self.get_directory(path)  # get target directory
        self.current_dir = directory
        self.location = path

    def show_dir(self, path):
        """Returns files of directory and x permission"""
        full_path = self.path_conversion(path)
        rwx, directory = self.get_directory(full_path)
        r, w, x = self.parse_rwx(rwx)
        if r == '1':
            return [x, self.read_directory(directory)]
        raise exeptions.PermissionsDenied()

    def login(self, login, password):
        """Authorization"""
        user = self.users.get(login)
        if user and user.password == hashlib.md5(bytes(password, 'ansi')).digest():
            self.user = user
        else:
            raise exeptions.IncorrectLoginOrPass()

    def logout(self):
        """Logout"""
        self.user = None

    def make_user(self, args):
        """Makes user and writes in file"""
        if not self.user.role:
            raise exeptions.PermissionsDenied()
        if len(args) != 3:
            raise exeptions.NotEnoughParams()
        if not args[2].isdigit():
            raise exeptions.WrongParams()
        if self.users.get(args[0].strip()):
            raise exeptions.UserExists(args[0].strip())
        password = hashlib.md5(bytes(args[1], 'ansi')).digest()
        user = User(login=args[0].strip(), password=password, role=int(args[2]), id=len(self.users) + 1)
        self.users[user.login.strip()] = user
        self.save_users()

    def remove_user(self, login):
        login = login.strip()
        if not self.users.get(login):
            raise exeptions.UserNotFound(login)
        if not self.user.role or login == 'root' or self.user.login.strip() == login:
            raise exeptions.PermissionsDenied()
        self.users.pop(login)
        self.save_users()

    """System functions"""

    def get_free_clusters(self, count=1):
        """Getting numbers of free clusters. Return a list of free clusters numbers"""
        clusters = list()
        with open('os.txt', 'rb') as file:
            file.seek(self.super_block.fat_offset)
            while len(clusters) < count and file.tell() != self.super_block.fat_copy_offset:
                if int.from_bytes(file.read(4), byteorder='big') == 0:
                    clusters.append(((file.tell() - self.super_block.fat_offset) // 4))
        if len(clusters) == count:
            return clusters
        print(colored('Not enough memory!', 'red'))

    def get_clusters_seq(self, first_cluster):
        result = [first_cluster]
        with open('os.txt', 'rb') as file:
            file.seek(self.super_block.fat_offset + (first_cluster - 1) * 4)
            num = int.from_bytes(file.read(4), byteorder='big')
            while num != self.super_block.clusters_count + 1:
                result.append(num)
                file.seek(self.super_block.fat_offset + (num - 1) * 4)
                num = int.from_bytes(file.read(4), byteorder='big')
        return result

    def get_cluster_count(self, data):
        """Return a count of required clusters"""
        if data:
            return math.ceil(len(data) / self.super_block.cluster_size)
        return 1

    def set_cluster_engaged(self, clusters):
        """Set cluster's status engaged"""
        with open('os.txt', 'r+b') as file:
            for i in range(len(clusters)-1):
                # write in FAT
                file.seek(self.super_block.fat_offset + (clusters[i] - 1) * 4)
                file.write(clusters[i+1].to_bytes(4, byteorder='big'))
                # write in FAT copy
                file.seek(self.super_block.fat_copy_offset + (clusters[i] - 1) * 4)
                file.write(clusters[i + 1].to_bytes(4, byteorder='big'))
            # write in FAT last cluster
            file.seek(self.super_block.fat_offset + (clusters[-1] - 1) * 4)
            file.write((self.super_block.clusters_count + 1).to_bytes(4, byteorder='big'))
            # write in FAT copy last cluster
            file.seek(self.super_block.fat_copy_offset + (clusters[-1] - 1) * 4)
            file.write((self.super_block.clusters_count + 1).to_bytes(4, byteorder='big'))

    def set_clusters_free(self, clusters):
        """Set cluster's status free"""
        with open('os.txt', 'r+b') as file:
            for cluster in clusters:
                # write in FAT
                file.seek(self.super_block.fat_offset + (cluster - 1) * 4)
                file.write((0).to_bytes(4, byteorder='big'))
                # write in FAT copy
                file.seek(self.super_block.fat_copy_offset + (cluster - 1) * 4)
                file.write((0).to_bytes(4, byteorder='big'))

    def read_directory(self, f):
        """Returns a list of files"""
        result = dict()
        clusters = self.get_clusters_seq(f.first_cluster)
        with open('os.txt', 'rb') as file:
            offset = (clusters.pop(0) - 1) * self.super_block.cluster_size
            file.seek(offset)
            while True:
                if file.tell() >= offset + self.super_block.cluster_size:
                    if not clusters:
                        break
                    offset = (clusters.pop(0)-1) * self.super_block.cluster_size
                    file.seek(offset)
                record = file.read(self.super_block.record_size)
                if not record.rstrip():
                    break
                if record[:1] != b' ':
                    f = File(file_bytes=record)
                    result[f.full_name] = f
        return result

    def read_file(self, f):
        data = b''
        clusters = self.get_clusters_seq(f.first_cluster)
        with open('os.txt', 'rb') as file:
            for cluster in clusters:
                file.seek((cluster-1) * self.super_block.cluster_size)
                data += file.read(self.super_block.cluster_size).strip()
        return data

    def get_directory(self, path):
        """Returns a File object of required directory"""
        rwx = 7
        path_list = path.split('/')
        path_list.pop(0)
        directory = self.super_block.main_dir
        files = self.read_directory(directory)
        for name in path_list:
            directory = files.get(name)
            if directory:
                rwx = self.get_mod(directory) & rwx
                files = self.read_directory(directory)
            else:
                raise exeptions.FileNotExists
        return [rwx, directory]

    def write_record(self, f, directory):
        """Write a file record"""
        clusters = self.get_clusters_seq(directory.first_cluster)
        with open('os.txt', 'r+b') as file:
            offset = (clusters.pop(0) - 1) * self.super_block.cluster_size
            file.seek(offset)
            while True:
                if file.tell() == offset + self.super_block.cluster_size:
                    if clusters:
                        offset = (clusters.pop(0) - 1) * self.super_block.cluster_size
                        file.seek(offset)
                    else:
                        return None
                record = file.read(self.super_block.record_size)
                if record[:1] == b' ':
                    file.seek(-self.super_block.record_size, 1)
                    file.write(f.get_file_bytes())
                    return True

    def write_data(self, clusters, data):
        with open('os.txt', 'r+b') as file:
            for cluster in clusters[:-1]:
                file.seek((cluster - 1) * self.super_block.cluster_size)
                file.write(data[0:self.super_block.cluster_size])
                data = data[self.super_block.cluster_size:]
            file.seek((clusters[-1] - 1) * self.super_block.cluster_size)
            file.write(data)

    def load_users(self):
        """Returns a dict of user's accounts"""
        users = dict()
        rwx, main_dir = self.get_directory('')
        file = self.read_directory(main_dir).get('users')
        data = self.read_file(file)
        for i in range(1, len(data) // 32 + 1):
            user = User(user_bytes=data[(i-1) * 32:i*32])
            users[user.login.strip()] = user
        return users

    def save_users(self):
        data = b''
        for user in self.users.values():
            data += user.get_user_bytes()
        rwx, main_dir = self.get_directory('')
        file = self.read_directory(main_dir).get('users')
        clusters = self.get_clusters_seq(file.first_cluster)
        data += b' ' * (len(clusters) * self.super_block.cluster_size - len(data))
        self.write_data(clusters, data)

    def path_conversion(self, path):
        if path and path != '/':
            path = self.location + '/' + path if path[0] != '/' else path
        elif path == '/':
            path = ''
        return path

    def get_mod(self, directory):
        if directory.uid == self.user.id:
            mod = int(directory.mod[1:4], 2)
        else:
            mod = int(directory.mod[4:], 2)
        return mod

    @staticmethod
    def parse_ext(name):
        pos = name.rfind('.')
        ext = ''
        if (-1) < pos < len(name)-1:
            ext = name[pos+1:]
            name = name[:pos]
        return [name, ext]

    @staticmethod
    def parse_rwx(rwx):
        string = bin(rwx)[2:]
        string = '0' * (3 - len(string)) + string
        return string

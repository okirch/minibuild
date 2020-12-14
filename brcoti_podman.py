#
# Build job running inside a container.
#
# This is a simplistic build script for building artefacts of various
# programming languages natively (eg using pip, npm etc) and upload the
# resulting artefacts to a local repo.
#
#   Copyright (C) 2020 Olaf Kirch <okir@suse.de>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#

import os
import os.path
import sys
import brcoti_core
import glob
import shutil

class PodmanCmd(object):
	def __init__(self, *args):
		self.cmd = "podman " + " ".join(args)

	def run(self, mode = None):
		cmd = self.cmd

		print("podman: " + self.cmd)
		sys.stdout.flush()

		if os.getuid() != 0:
			cmd = "sudo -- " + cmd

		if mode is None:
			return os.system(cmd)
		return os.popen(cmd, mode = mode)

	def popen(self, mode = 'r'):
		cmd = self.cmd

		print("podman: " + self.cmd)
		sys.stdout.flush()

		if os.getuid() != 0:
			cmd = "sudo -- " + cmd
		return os.popen(cmd, mode = mode)

class PodmanCompute(brcoti_core.Compute):
	def __init__(self, global_config, config):
		super(PodmanCompute, self).__init__(global_config, config)
		self.network_up = False

	def spawn(self, flavor):
		img_config = self.config.get_image(flavor)

		self.pod_name = self.config.pod.name

		if not self.network_up:
			self.setup_network()
			self.network_up = True

		print("%s: using image %s to build %s package" % (self.config.name, img_config.image, flavor))
		return PodmanComputeNode(img_config, self)

	def setup_network(self):
		self.network_name = self.config.network.name
		if self.network_name is None:
			print("podman: using default podman network")
			return

		with brcoti_core.popen("podman network ls") as f:
			if any(l.split()[0] == self.network_name for l in f.readlines()):
				return

		print("podman: setting up network \"%s\"" % self.network_name)
		brcoti_core.run_command("podman network create %s" % self.network_name)

class PodmanPathMixin:
	def __init__(self, root):
		self.root = root

	def __repr__(self):
		return "container:" + self.path

	def _realpath(self, path):
		if path is None:
			path = self.path
		if not path.startswith('/'):
			path = os.path.join(self.path, path)
		return path

	def _hostpath(self, path):
		return self.root + self._realpath(path)

	def hostpath(self):
		return self.root + self.path

class PodmanFile(PodmanPathMixin, brcoti_core.ComputeResourceFile):
	def __init__(self, root, path):
		PodmanPathMixin.__init__(self, root)

		assert(path.startswith('/'))
		brcoti_core.ComputeResourceFile.__init__(self, path)

	def open(self, mode = 'r'):
		path = self.hostpath()
		return open(path, mode)

class PodmanDirectory(PodmanPathMixin, brcoti_core.ComputeResourceDirectory):
	def __init__(self, root, path):
		PodmanPathMixin.__init__(self, root)

		assert(path.startswith('/'))
		brcoti_core.ComputeResourceDirectory.__init__(self, path)

	def glob_files(self, path_pattern):
		result = []

		path_pattern = self._hostpath(path_pattern)
		for name in glob.glob(path_pattern):
			assert(name.startswith(self.root))
			try:
				name = name.removeprefix(self.root)
			except:
				name = name[len(self.root):]

			fh = self.lookup(name)
			if not fh:
				raise ValueError("glob returns \"%s\" which does not seem to be a valid (relative) path" % (name))
			result.append(fh)
		return result

	def lookup(self, path):
		path = self._realpath(path)

		hp = self._hostpath(path)
		if not os.path.exists(hp):
			return None
		if os.path.isdir(hp):
			return PodmanDirectory(self.root, path)
		return PodmanFile(self.root, path)

	def open(self, path, mode = 'r'):
		path = self._realpath(path)
		path = self._hostpath(path)
		return open(path, mode)

class PodmanComputeNode(brcoti_core.ComputeNode):
	def __init__(self, img_config, backend):
		super(PodmanComputeNode, self).__init__(backend)

		self.container_id = None
		self.container_root = None
		self.env = {}

		# FIXME: make this configurable
		self.build_user = "build:build"

		# For now, only root can do this. Sorry.
		if os.getuid() != 0:
			raise ValueError("podman backend: you need to be root to use this backend")

		# Kludge to make https://localhost URLs work in the container
		self._mapped_hostname = None

		self.start(img_config, backend.network_name, backend.pod_name)

		print("Created container %s; root=%s" % (self.container_id, self.container_root))

	def __del__(self):
		if not self.cleanup_on_exit:
			return

		if self.container_root:
			PodmanCmd("umount", self.container_id).run()
		if self.container_id:
			PodmanCmd("stop", self.container_id).run()

	def start(self, img_config, network_name, pod_name):
		assert(self.container_id is None)
		assert(network_name is None or pod_name is None)

		self.setup_localhost_mapping()

		args = ["--rm", "-d"]
		for host in self.hosts:
			args.append("--add-host %s" % host)
		if network_name:
			args += ("--network", network_name)
		if pod_name:
			args += ("--pod", pod_name)

		# For debugging
		args += ('--cap-add', 'sys_ptrace')

		args.append(img_config.image)

		f = PodmanCmd("run", " ".join(args)).popen()
		self.container_id = f.read().strip()
		assert(self.container_id)

		f = PodmanCmd("mount", self.container_id).popen()
		self.container_root = f.read().strip()
		assert(self.container_root)

		ca_certificates = self.backend.global_config.globals.certificates
		self.publish_system_certificates(ca_certificates)
		self.publish_python_certificates(ca_certificates)
		self.publish_ruby_certificates(ca_certificates)

	def publish_system_certificates(self, ca_certificates):
		for ca_path in ca_certificates:
			shutil.copy(ca_path, self.container_root + "/usr/share/pki/trust/anchors")

		self.run_command("/usr/sbin/update-ca-certificates", working_dir = None, privileged_user = True)

	def publish_python_certificates(self, ca_certificates):
		cert_string = ""
		for ca_path in ca_certificates:
			print("Reading certificate from %s" % ca_path)
			with open(ca_path) as f:
				cert_string += "\n"
				cert_string += f.read()

		if not cert_string:
			return

		path_list = glob.glob(self.container_root + "/usr/lib/python*/site-packages/pip/_vendor/certifi/cacert.pem")
		for bundle_path in path_list:
			print("Updating %s" % path_list)
			with open(bundle_path, "a") as f:
				f.write(cert_string)

	def publish_ruby_certificates(self, ca_certificates):
		path_list = glob.glob(self.container_root + "/usr/lib64/ruby/*/rubygems/ssl_certs/rubygems.org")
		for ca_path in ca_certificates:
			for dst_path in path_list:
				dst_path = os.path.join(dst_path, os.path.basename(ca_path))
				print("Installing %s to container:%s" % (ca_path, dst_path))
				shutil.copy(ca_path, dst_path)

	def translate_url(self, url):
		import urllib.parse
		import socket

		parsed_url = urllib.parse.urlparse(url)
		if parsed_url.hostname != 'localhost':
			return url

		self._mapped_hostname = socket.getfqdn()

		if parsed_url.port:
			netloc = "%s:%s" % (self._mapped_hostname, parsed_url.port)
		else:
			netloc = self._mapped_hostname

		parsed_url = parsed_url._replace(netloc = netloc)
		result = urllib.parse.urlunparse(parsed_url)

		print("translated url \"%s\" -> \"%s\"" % (url, result))
		return result

	def trusted_hosts(self):
		if self._mapped_hostname:
			return [self._mapped_hostname]
		return []

	def setup_localhost_mapping(self):
		self.hosts = []

	def putenv(self, name, value):
		self.env[name] = value

	def interactive_shell(self, working_dir = None):
		cmd = brcoti_core.ShellCommand("/bin/bash")
		cmd.working_dir = working_dir
		cmd.privileged_user = True
		self._make_command(cmd, mode = "shell").run()

	def _make_command(self, shellcmd, mode = None):
		args = []

		working_dir = shellcmd.working_dir
		if working_dir:
			if isinstance(working_dir, brcoti_core.ComputeResourceFS):
				working_dir = working_dir.path
			args.append("--workdir \'%s\'" % working_dir)

		for name, value in shellcmd.environ.items():
			args.append(" --env %s='%s'" % (name, value))

		if not shellcmd.no_default_env:
			for name, value in self.env.items():
				args.append(" --env %s='%s'" % (name, value))

		if not shellcmd.privileged_user:
			args.append(" --user %s" % self.build_user)
		if mode is not None:
			if mode == 'shell':
				args.append(" -it")
			elif mode.startswith('w'):
				args.append(" --interactive")
		args.append(self.container_id)

		return PodmanCmd("exec", *args, shellcmd.cmd)

	def _exec(self, shellcmd, mode = None):
		return self._make_command(shellcmd, mode).run(mode)

	def get_directory(self, path):
		assert(path.startswith('/'))

		if not os.path.isdir(self.container_root + path):
			raise ValueError("%s is not a directory (inside the container)" % (path))
		return PodmanDirectory(self.container_root, path)

	def shutdown(self):
		pass

def compute_factory(global_config, config):
        return PodmanCompute(global_config, config)



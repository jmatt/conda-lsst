#
# Quick script to bootstrap a clean build environment
# MUST be run from the root package directory
#

set -e

trap '{ test -f .bootstrap.msg && cat .bootstrap.msg; rm -f .bootstrap.msg; }' EXIT

if hash conda 2>/dev/null; then
	echo 'Detected existing conda on $PATH:'
	echo
	echo "    $(which conda)"
	echo
	echo 'Having multiple Conda installs on the path is not recommended.'
	echo 'Remove it and try again.'
	exit -1
fi

#
# Install Miniconda
#

if [[ ! -f "$PWD/miniconda/.installed" ]]; then
	case "$OSTYPE" in
		linux*)  MINICONDA_SH=Miniconda2-latest-Linux-x86_64.sh ;;
		darwin*) MINICONDA_SH=Miniconda2-latest-MacOSX-x86_64.sh ;;
		*)       echo "Unsupported OS $OSTYPE. Exiting."; exit -1 ;;
	esac

	rm -f "$MINICONDA_SH"
	rm -rf "$PWD/miniconda"
	curl -O https://repo.continuum.io/miniconda/"$MINICONDA_SH"
	bash "$MINICONDA_SH" -b -p "$PWD/miniconda"
	rm -f "$MINICONDA_SH"

	#
	# Install prerequisites
	#
	export PATH="$PWD/miniconda/bin:$PATH"
	conda install conda-build==1.20.0 jinja2 requests sqlalchemy pip pyyaml --yes
	# Install python future specifically from conda-forge.
	# See: https://github.com/ContinuumIO/anaconda-issues/issues/478
	conda install -c conda-forge future --yes
	# This switches conda and conda-env. Switch back.
	conda install conda==4.2.16 --yes

	#
	# Conda build and install SWIG 3.0.10
	#
	if [ -z "${CONDA_LSST_OLD_SWIG}" ]; then
 	   conda build ./etc/recipes/swig
	   conda install --use-local swig --yes
	else
	   conda install swig==3.0.2 --yes
	   sed -i "" "s/==3\.0\.10/==3\.0\.2/g" ./etc/config.yaml
	fi

	#
	# Pip install requests_file
	#
	pip install requests_file

	# marker that we're done
	touch "$PWD/miniconda/.installed"
else
	echo
	echo "Found Miniconda in $PWD/miniconda; skipping Miniconda install."
	echo
fi

# Install conda==4.1.12 so it'll work with conda-lsst.
conda install conda==4.1.12

echo "Miniconda has been installed in $PWD/miniconda. Add it to your path:"
echo
echo "  export PATH=\"\${PWD}/bin:\${PWD}/miniconda/bin:\${PATH}\""
echo
echo "and continue."

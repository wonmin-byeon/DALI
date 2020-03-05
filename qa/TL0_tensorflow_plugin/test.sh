#!/bin/bash -e
# used pip packages
pip_packages="nose tensorflow-gpu"
target_dir=./dali/test/python

# populate epilog and prolog with variants to enable/disable conda and virtual env
# every test will be executed for bellow configs
prolog=(: enable_conda enable_virtualenv)
epilog=(: disable_conda disable_virtualenv)

test_body() {
    # Manually removing the supported plugin so that it fails
    lib_dir=$(python -c 'import nvidia.dali.sysconfig as sc; print(sc.get_lib_dir())')
    rm -rf $lib_dir/plugin/*.so

    # No plugin installed, should fail
    nosetests --verbose test_dali_tf_plugin.py:TestDaliTfPluginLoadFail

    # Installing "current" dali tf (built against installed TF)
    pip install ../../../nvidia-dali-tf-plugin*.tar.gz
    nosetests --verbose test_dali_tf_plugin.py:TestDaliTfPluginLoadOk

    # DALI TF run
    nosetests --verbose test_dali_tf_plugin_run.py

    # DALI TF DATASET run
    nosetests --verbose test_dali_tf_dataset.py

    nosetests --verbose test_dali_tf_dataset_shape.py
}

pushd ../..
source ./qa/test_template.sh
popd

Examples
========

Here are some examples that demonstrate how to run models using pymt.
The examples in the first list run only single models. While the models
do not couple with other models, they may couple with external data
sets. The examples in the second list show how multiple models
can be coupled together by exchanging data.

If you would like to run these examples yourself, in addition to
`installing pymt <installation.rst#Installation>`_, you will
have to first install Jupyter notebook:

.. code-block:: bash

    $ conda install notebook


Single Models
-------------

.. toctree::
   :titlesonly:

   demos/frost_number
   demos/ku
   demos/cem
   demos/child
   demos/hydrotrend
   demos/sedflux3d
   demos/subside

Coupled Models
--------------

.. toctree::
   :titlesonly:

   demos/cem_and_waves
   demos/sedflux3d_and_child

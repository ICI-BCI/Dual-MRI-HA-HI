# Dual-MRI-HA-HI

# HA-HI: Synergising fMRI and DTI for MCI Diagnosis

Welcome to the official repository for the HA-HI (Hierarchical Alignments and Hierarchical Interactions) project. This repository hosts the code used in the research paper titled “HA-HI: Synergising fMRI and DTI through Hierarchical Alignments and Hierarchical Interactions for Mild Cognitive Impairment Diagnosis.”

## Overview

The HA-HI project represents a novel approach in medical imaging and computational neuroscience, focusing on the diagnosis of early-stage cognitive impairments, such as Mild Cognitive Impairment (MCI) and Subjective Cognitive Decline (SCD). Our method combines functional Magnetic Resonance Imaging (fMRI) and Diffusion Tensor Imaging (DTI) to enhance diagnostic accuracy and understanding of MCI and SCD. The project applies hierarchical alignments and interactions between fMRI and DTI data, aiming to extract and integrate patterns more indicative of MCI and SCD from dual-modal MRI.

## Research Paper

This repository is directly linked to our academic research. The paper detailing the methodologies, experiments, and results can be accessed at [link to the paper]. We encourage users to read the paper for a comprehensive understanding of the project's scientific background and objectives.

## Key Features

- **Data Processing Pipeline:** Includes scripts for preprocessing and analyzing fMRI and DTI data.
- **Hierarchical Alignments and Interactions Framework:** Implements the novel approach for aligning dual-modal imaging data.
- **Interpretability Analysis Tool:** Provides a tool for evaluating significant brain connectivities and regions impacted by cognitive impairments, aiding in the understanding of MCI and SCD


## Environment

To ensure compatibility and optimal performance, please install the following dependencies in your environment:

```diff
- torch == 1.13.1
- numpy == 1.22.3
- nibabel == 1.10.2
- torchcam == 0.3.2
- torchvision == 0.14.1
- einops == 0.6.0
- python == 3.9.0
- imageio == 2.31.1
```

## Extracting Imaging Features

To prepare the data for the model, you need to extract the static functional connectivity (sfc), dynamic functional connectivity (dfc), and amplitude of low-frequency fluctuations (alff) using Matlab. This can be accomplished efficiently with the batch operations in `spm12`. For generating Fractional Anisotropy (FA), `PANDA` is recommended, although `FSL` is a viable alternative. Note that the input data shape may affect the kernel size in the average pooling layer. Adjust the kernel size as needed to avoid bugs.

## Running the Model

### Creating K-Fold CSV File

Generate the necessary CSV files for model training using the following script:

```diff
+ generate_csv.py
```

### Training and Validating the Model

Train and validate the model by executing:

```diff
+ train.py
```

### Testing the Model

For model testing, use:

```diff
+ test.py
```

## Generating Activation Maps in Multi-Modal MRI

To visualize the activation maps in multi-modal MRI, follow these steps:

### Replace Torchcam Files

Replace the original files in the torchcam package with the modified versions found in the `method` folder of this repository, including:

```diff
+ activation.py
+ core.py
```

### Run the Test Script

Execute the following script to generate activation maps:

```diff
+ test.py
```

### Viewing Results

The resulting images can be found in the `images` folder of this repository.

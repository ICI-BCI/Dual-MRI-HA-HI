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

## __Environment__  
```diff  
torch ==1.13.1
numpy == 1.22.3  
nibabel == 1.10.2  
torchcam == 0.3.2  
torchvision == 0.14.1  
einops == 0.6.0  
python == 3.9.0  
imageio == 2.31.1
``` 
## extract the imaging features
To run the model, you need to extract the sfc, dfc, and alff by Matlab. You can use the batch operation of spm12 to finish this. Then, you need to use Panda to generate FA. But you can also use FSL instead. Additionally, the input data shape might influence the kernel size of avgpooling, you need to change the kernel size, if has bugs.  

## run the model

### __Create k fold csv file__  
```diff
generate_csv.py
```
### train and validate the model 
```diff
train.py
```
### test the model 
```diff
test.py
```
## generate the avtivation map in multi-modal MRI  
### replace the py files in initial torchcam package with the files in $\color[rgb]{1,0,1} method$ folder in this respority, including
```diff
activation.py  
core.py
```
### run test.py  
```diff
test.py
```
### results
```diff
see the images folder
```

# Copyright (C) 2020-2022, François-Guillaume Fernandez.

# This program is licensed under the Apache License 2.0.
# See LICENSE or go to <https://www.apache.org/licenses/LICENSE-2.0> for full license details.

import logging
import math
from typing import Any, List, Optional, Tuple, Union

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from ._utils import locate_linear_layer
from .core import _CAM

__all__ = ["CAM", "ScoreCAM", "SSCAM", "ISCAM"]


class CAM(_CAM):
    r"""Implements a class activation map extractor as described in `"Learning Deep Features for Discriminative
    Localization" <https://arxiv.org/pdf/1512.04150.pdf>`_.

    The Class Activation Map (CAM) is defined for image classification models that have global pooling at the end
    of the visual feature extraction block. The localization map is computed as follows:

    .. math::
        L^{(c)}_{CAM}(x, y) = ReLU\Big(\sum\limits_k w_k^{(c)} A_k(x, y)\Big)

    where :math:`A_k(x, y)` is the activation of node :math:`k` in the target layer of the model at
    position :math:`(x, y)`,
    and :math:`w_k^{(c)}` is the weight corresponding to class :math:`c` for unit :math:`k` in the fully
    connected layer..

    >>> from torchvision.models import resnet18
    >>> from torchcam.methods import CAM
    >>> model = resnet18(pretrained=True).eval()
    >>> cam = CAM(model, 'layer4', 'fc')
    >>> with torch.no_grad(): out = model(input_tensor)
    >>> cam(class_idx=100)

    Args:
        model: input model
        target_layer: either the target layer itself or its name, or a list of those
        fc_layer: either the fully connected layer itself or its name
        input_shape: shape of the expected input tensor excluding the batch dimension
    """

    def __init__(
        self,
        model: nn.Module,
        target_layer: Optional[Union[Union[nn.Module, str], List[Union[nn.Module, str]]]] = None,
        fc_layer: Optional[Union[nn.Module, str]] = None,
        input_shape: Tuple[int, ...] = (3, 224, 224),
        **kwargs: Any,
    ) -> None:

        if isinstance(target_layer, list) and len(target_layer) > 1:
            raise ValueError("base CAM does not support multiple target layers")

        super().__init__(model, target_layer, input_shape, **kwargs)

        if isinstance(fc_layer, str):
            fc_name = fc_layer
        # Find the location of the module
        elif isinstance(fc_layer, nn.Module):
            fc_name = self._resolve_layer_name(fc_layer)
        # If the layer is not specified, try automatic resolution
        elif fc_layer is None:
            fc_name = locate_linear_layer(model)  # type: ignore[assignment]
            # Warn the user of the choice
            if isinstance(fc_name, str):
                logging.warning(f"no value was provided for `fc_layer`, thus set to '{fc_name}'.")
            else:
                raise ValueError("unable to resolve `fc_layer` automatically, please specify its value.")
        else:
            raise TypeError("invalid argument type for `fc_layer`")
        # Softmax weight
        self._fc_weights = self.submodule_dict[fc_name].weight.data
        # squeeze to accomodate replacement by Conv1x1
        if self._fc_weights.ndim > 2:
            self._fc_weights = self._fc_weights.view(*self._fc_weights.shape[:2])

    @torch.no_grad()
    def _get_weights(
        self,
        class_idx: Union[int, List[int]],
        *args: Any,
    ) -> List[Tensor]:
        """Computes the weight coefficients of the hooked activation maps."""

        # Take the FC weights of the target class
        if isinstance(class_idx, int):
            return [self._fc_weights[class_idx, :].unsqueeze(0)]
        else:
            return [self._fc_weights[class_idx, :]]


class ScoreCAM(_CAM):
    r"""Implements a class activation map extractor as described in `"Score-CAM:
    Score-Weighted Visual Explanations for Convolutional Neural Networks" <https://arxiv.org/pdf/1910.01279.pdf>`_.

    The localization map is computed as follows:

    .. math::
        L^{(c)}_{Score-CAM}(x, y) = ReLU\Big(\sum\limits_k w_k^{(c)} A_k(x, y)\Big)

    with the coefficient :math:`w_k^{(c)}` being defined as:

    .. math::
        w_k^{(c)} = softmax\Big(Y^{(c)}(M_k) - Y^{(c)}(X_b)\Big)_k

    where :math:`A_k(x, y)` is the activation of node :math:`k` in the target layer of the model at
    position :math:`(x, y)`, :math:`Y^{(c)}(X)` is the model output score for class :math:`c` before softmax
    for input :math:`X`, :math:`X_b` is a baseline image,
    and :math:`M_k` is defined as follows:

    .. math::
        M_k = \frac{U(A_k) - \min\limits_m U(A_m)}{\max\limits_m  U(A_m) - \min\limits_m  U(A_m)})
        \odot X_b

    where :math:`\odot` refers to the element-wise multiplication and :math:`U` is the upsampling operation.

    >>> from torchvision.models import resnet18
    >>> from torchcam.methods import ScoreCAM
    >>> model = resnet18(pretrained=True).eval()
    >>> cam = ScoreCAM(model, 'layer4')
    >>> with torch.no_grad(): out = model(input_tensor)
    >>> cam(class_idx=100)

    Args:
        model: input model
        target_layer: either the target layer itself or its name, or a list of those
        batch_size: batch size used to forward masked inputs
        input_shape: shape of the expected input tensor excluding the batch dimension
    """

    def __init__(
        self,
        model: nn.Module,
        target_layer: Optional[Union[Union[nn.Module, str], List[Union[nn.Module, str]]]] = None,
        batch_size: int = 32,
        input_shape: Tuple[int, ...] = (3, 224, 224),
        **kwargs: Any,
    ) -> None:

        super().__init__(model, target_layer, input_shape, **kwargs)

        # Input hook
        self.hook_handles.append(model.register_forward_pre_hook(self._store_input))
        self.bs = batch_size
        # Ensure ReLU is applied to CAM before normalization
        self._relu = True

    def _store_input(self, module: nn.Module, input: Tensor) -> None:
        """Store model input tensor."""

        if self._hooks_enabled:
            if len(input[0])>1:
                self._input = input[0].copy()
            else:
               self._input = input[0].data.clone()

    @torch.no_grad()
    def _get_score_weights(self, activations: List[Tensor], class_idx: Union[int, List[int]]) -> List[Tensor]:

        b, c = activations[0].shape[1:3]#b,c means
        score_input_list=list()
        weights_list = list()
        for i in range(len(activations)):
            b, c = activations[i].shape[:2]
            weights = torch.zeros((b,c), dtype=activations[i].dtype).to(device=activations[i].device)
            weights_list.append(weights)
        idcs_list = list()
        for i in range(len(activations)):
            b, c = activations[i].shape[:2]
            idcs = torch.arange(b).repeat_interleave(c)
            idcs_list.append(idcs)
        # (N * C, I, H, W)
        # for act in activations[0]:
        #     scored_inputs = [
        #         (act.unsqueeze(2) * torch.unsqueeze(torch.squeeze(self._input[0][3][0]).cuda(),dim=2)).view(b * c, *self._input[0][3].shape[1:])
        #       ].view(b * c, *self._input[0][3].shape[1:]
        # scored_inputs = [(act.unsqueeze(2) * torch.unsqueeze(torch.squeeze(self._input[0][3][0]).cuda(),dim=2))
        #                     for act in activations[0]]
        # compute on singe channel leading to OOM
        for i in range(len(activations)):
            b,c = activations[i].shape[:2]
            # b = 1
            h,w,d= self._input[0][i].shape[2:]
            score_input =torch.zeros([b,c,h,w,d])
            #.view(b * c, h,w,d) activations[i][0,...].cpu()*self._input[0][i][0,...].cpu()+
            # activations[i][1, ...].cpu() * self._input[0][i][1, ...].cpu()+
            score_input_0 = (activations[i][0,...].cpu() * 10 +  self._input[0][i][0,...].cpu()).unsqueeze(0)
            score_input_1 = (activations[i][1, ...].cpu() * 10+  self._input[0][i][1, ...].cpu() ).unsqueeze(0)
            score_input = torch.cat([score_input_0,score_input_1],dim=0)
            # for batch in range(1,activations[i].shape[0]):
            #     for channel in range(1,activations[i].shape[1]):
            #         score_input_tmp = (activations[i][batch,channel,:,:,:]*self._input[0][i][batch,0,...].cuda()).unsqueeze(0)
            #         score_input =torch.cat([score_input,score_input_tmp],dim=0)
            # score_input =  [activations[i][:,c,:,:,:].cpu().numpy() * self._input[0][i].cpu().numpy() for c in range(activations[i].shape[1]-1)]
            # score_input_0 = torch.mul(activations[i][0],self._input[0][i][0].cuda()).view(1 * c, h,w,d)
            # del activations[i][0], score_input_0
            # score_input_1 = torch.mul(activations[i][1], self._input[0][i][1].cuda()).view(1 * c, h, w, d)
            # score_input = torch.cat([score_input_0.unsqueeze(0),score_input_0.unsqueeze(0)],dim=0)
            score_input_list.append(score_input)
            # del
        # scored_inputs = torch.mul(activations.unsqueeze(1),self._input[0][3])
        # Initialize weights
        # (N * C)


           # weights = [torch.zeros(b * c, dtype=t.dtype).to(device=t.device) for t in activations]

        # (N, M)
        # .repeat_interleave((score_input_list[0][0].shape[0]/score_input_list[0][1].shape[0])-1,dim=1)
        if score_input_list[1].shape[1] != 512:
            score_input_list[1] = score_input_list[1].repeat_interleave(int(score_input_list[0].shape[1]/score_input_list[1].shape[1]),dim=1)
        logits = self.model(self._input)
        # # idcs = torch.arange(b).repeat_interleave(c)
        for channel in range(score_input_list[0][0].shape[0]):

        # for idx, scored_input in enumerate(scored_inputs):
        #     for _idx in range(math.ceil(weights[channel].numel() / self.bs)):
                # _slice = slice(_idx * self.bs, min((_idx + 1) * self.bs, weights[channel].numel()))
                slice_input = [score_input_list[0][:,channel,:,:,:].unsqueeze(1).cuda(),
                               score_input_list[1][:,channel,:,:,:].unsqueeze(1).cuda(),
                               score_input_list[2][:,channel,:,:,:].unsqueeze(1).cuda(),
                               score_input_list[3][:,channel,:,:,:].unsqueeze(1).cuda()]
                slice_input = [slice_input, self._input[1]]
                # cic = self.model(slice_input)
                cic = self.model(slice_input)[1]-logits[1]
                if isinstance(class_idx, int):
                    try:
                        weights[:,channel] = cic[:, class_idx]
                    except RuntimeError:
                        weights[:,channel] = cic[:, class_idx]
                else:
                    _target = torch.tensor(class_idx, device=cic.device)[idcs[_slice]]
                    weights[idx][_slice] = cic.gather(1, _target.view(-1, 1)).squeeze(1)
        #     # Process by chunk (GPU RAM limitation)
        #     for _idx in range(math.ceil(weights[idx].numel() / self.bs)):
        #
        #         _slice = slice(_idx * self.bs, min((_idx + 1) * self.bs, weights[idx].numel()))
        #         # Get the softmax probabilities of the target class
        #         # (*, M)
        #         cic = self.model(scored_input[_slice]) - logits[idcs[_slice]]
        #         if isinstance(class_idx, int):
        #             weights[idx][_slice] = cic[:, class_idx]
        #         else:
        #             _target = torch.tensor(class_idx, device=cic.device)[idcs[_slice]]
        #             weights[idx][_slice] = cic.gather(1, _target.view(-1, 1)).squeeze(1)

        # Reshape the weights (N, C)
        weights = torch.where(torch.isnan(weights), torch.full_like(weights, 0), weights)
        return torch.softmax(weights, 1)

    @torch.no_grad()
    def _get_weights(
        self,
        class_idx: Union[int, List[int]],
        *args: Any,
    ) -> List[Tensor]:
        """Computes the weight coefficients of the hooked activation maps."""

        self.hook_a: List[Tensor]  # type: ignore[assignment]#是一个类型注解，用于指示 self.hook_a 是一个列表（List）类型，其中包含 Tensor 对象
        # self.hook_g: List[Tensor]
        # Normalize the activation
        # (N, C, H', W')
        upsampled_a_list = list()
        activation_list = list()
        shape_ =list()
        shape_list = [[4,3,2],[3,3,1],[11,6,1],[6,3,1]]
        shape_list_single = [[4,3,2],[11,6,4],[11,6,1],[6,3,1]]
        shape_list_multiscale = [[41,41,30],[41,41,6],[21,21,3],[6,6,1],[11,11,2]]
        # shape_alff =
        # shape_dfc =
        # shape_fc =
        # shape_fc =
        single_ = False
        dfc_ = False
        multi_scale = False
        for act in set(self.hook_a_list):
            if act.shape in shape_:
                continue
            activation_a = [self._normalize(act, act.ndim - 2)]
            shape_tmp = activation_a[0][0,0,...].cpu().shape
            # index_ = shape_list.index([shape_tmp[0],shape_tmp[1],shape_tmp[2]])
            try :
                index_ = shape_list.index([shape_tmp[0],shape_tmp[1],shape_tmp[2]])
                single_ = True
            except ValueError:
                try :
                    index_ = shape_list_single.index([shape_tmp[0],shape_tmp[1],shape_tmp[2]])
                    dfc_ = True
                except ValueError:
                    try :
                       index_ = shape_list_multiscale.index([shape_tmp[0], shape_tmp[1], shape_tmp[2]])
                       index_ = 1
                    except ValueError:
                        print('no value')
                    # if len(index_) > 0:
                    #     index_ = 1
                    multi_scale = True
            activation_list.insert(index_, activation_a[0])
            # upsampled_a_list.append(activation_a)
            shape_.append(act.shape)
        # exchange activation map
        # upsampled_a_tmp = upsampled_a_list[3]
        # upsampled_a_list[3] = upsampled_a_list[1]
        # upsampled_a_list[1] = upsampled_a_tmp
        # upsampled_a_tmp = upsampled_a_list[3]
        # upsampled_a_list[3] = upsampled_a_list[2]
        # upsampled_a_list[3] = upsampled_a_tmp
        activations = activation_list.copy()
        # upsampled_a = [self._normalize(act, act.ndim - 2) for act in self.hook_a]
        # upsampled_a = upsampled_a[0][0,:,:,:,:]
        # upsampled_a = torch.mean(upsampled_a[0], dim=1)
        # Upsample it to input_size
        # (N, C, H, W)
        spatial_dims = self._input[0][3].ndim - 2
        interpolation_mode = "bilinear" if spatial_dims == 2 else "trilinear" if spatial_dims == 3 else "nearest"
        # doesn't need to three situation
        if single_ == True and dfc_ ==False:
            for i in range(len(upsampled_a_list)):
                upsampled_a_list[i]= F.interpolate(upsampled_a_list[i], self._input[0][i].shape[2:], mode="trilinear",
                                             align_corners=False)
        elif single_ == True and dfc_ == True and multi_scale == False:
            for i in range(len(upsampled_a_list)):
                upsampled_a_list[i]= F.interpolate(upsampled_a_list[i], self._input[0][i].shape[2:], mode="trilinear",
                                             align_corners=False)
        else:
            for i in range(len(upsampled_a_list)):
                upsampled_a_list[i] = F.interpolate(upsampled_a_list[i], self._input[0][i].shape[2:], mode="trilinear",
                                                    align_corners=False)
        # upsampled_a= F.interpolate(torch.squeeze(upsampled_a[0]), self._input[0][3].shape[2:4], mode="bilinear",
        #                                  align_corners=False)

        # for up_a in upsampled_a:
        #     upsampled_a_test = F.interpolate(torch.squeeze(upsampled_a), self._input[0][3].shape[2:4], mode="bilinear", align_corners=False)


        # Disable hook updates
        self._hooks_enabled = False
        # Switch to eval
        origin_mode = self.model.training
        self.model.eval()

        weights = self._get_score_weights(upsampled_a_list, class_idx)

        # Reenable hook updates
        self._hooks_enabled = True
        # Put back the model in the correct mode
        self.model.training = origin_mode

        return weights, activations

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(batch_size={self.bs})"


class SSCAM(ScoreCAM):
    r"""Implements a class activation map extractor as described in `"SS-CAM: Smoothed Score-CAM for
    Sharper Visual Feature Localization" <https://arxiv.org/pdf/2006.14255.pdf>`_.

    The localization map is computed as follows:

    .. math::
        L^{(c)}_{SS-CAM}(x, y) = ReLU\Big(\sum\limits_k w_k^{(c)} A_k(x, y)\Big)

    with the coefficient :math:`w_k^{(c)}` being defined as:

    .. math::
        w_k^{(c)} = softmax\Big(\frac{1}{N} \sum\limits_{i=1}^N (Y^{(c)}(\hat{M_k}) - Y^{(c)}(X_b))\Big)_k

    where :math:`N` is the number of samples used to smooth the weights,
    :math:`A_k(x, y)` is the activation of node :math:`k` in the target layer of the model at
    position :math:`(x, y)`, :math:`Y^{(c)}(X)` is the model output score for class :math:`c` before softmax
    for input :math:`X`, :math:`X_b` is a baseline image,
    and :math:`M_k` is defined as follows:

    .. math::
        \hat{M_k} = \Bigg(\frac{U(A_k) - \min\limits_m U(A_m)}{\max\limits_m  U(A_m) - \min\limits_m  U(A_m)} +
        \delta\Bigg) \odot X_b

    where :math:`\odot` refers to the element-wise multiplication, :math:`U` is the upsampling operation,
    :math:`\delta \sim \mathcal{N}(0, \sigma^2)` is the random noise that follows a 0-mean gaussian distribution
    with a standard deviation of :math:`\sigma`.

    >>> from torchvision.models import resnet18
    >>> from torchcam.methods import SSCAM
    >>> model = resnet18(pretrained=True).eval()
    >>> cam = SSCAM(model, 'layer4')
    >>> with torch.no_grad(): out = model(input_tensor)
    >>> cam(class_idx=100)

    Args:
        model: input model
        target_layer: either the target layer itself or its name, or a list of those
        batch_size: batch size used to forward masked inputs
        num_samples: number of noisy samples used for weight computation
        std: standard deviation of the noise added to the normalized activation
        input_shape: shape of the expected input tensor excluding the batch dimension
    """

    def __init__(
        self,
        model: nn.Module,
        target_layer: Optional[Union[Union[nn.Module, str], List[Union[nn.Module, str]]]] = None,
        batch_size: int = 32,
        num_samples: int = 35,
        std: float = 2.0,
        input_shape: Tuple[int, ...] = (3, 224, 224),
        **kwargs: Any,
    ) -> None:

        super().__init__(model, target_layer, batch_size, input_shape, **kwargs)

        self.num_samples = num_samples
        self.std = std
        self._distrib = torch.distributions.normal.Normal(0, self.std)

    @torch.no_grad()
    def _get_score_weights(self, activations: List[Tensor], class_idx: Union[int, List[int]]) -> List[Tensor]:

        b, c = activations[0].shape[:2]

        # Initialize weights
        # (N * C)
        weights = [torch.zeros(b * c, dtype=t.dtype).to(device=t.device) for t in activations]

        # (N, M)
        logits = self.model(self._input)
        idcs = torch.arange(b).repeat_interleave(c)

        for idx, act in enumerate(activations):
            # Add noise
            for _ in range(self.num_samples):
                noise = self._distrib.sample(act.size()).to(device=act.device)
                # (N, C, I, H, W)
                scored_input = (act + noise).unsqueeze(2) * self._input.unsqueeze(1)
                # (N * C, I, H, W)
                scored_input = scored_input.view(b * c, *scored_input.shape[2:])

                # Process by chunk (GPU RAM limitation)
                for _idx in range(math.ceil(weights[idx].numel() / self.bs)):

                    _slice = slice(_idx * self.bs, min((_idx + 1) * self.bs, weights[idx].numel()))
                    # Get the softmax probabilities of the target class
                    cic = self.model(scored_input[_slice]) - logits[idcs[_slice]]
                    if isinstance(class_idx, int):
                        weights[idx][_slice] += cic[:, class_idx]
                    else:
                        _target = torch.tensor(class_idx, device=cic.device)[idcs[_slice]]
                        weights[idx][_slice] += cic.gather(1, _target.view(-1, 1)).squeeze(1)

        # Reshape the weights (N, C)
        return [torch.softmax(weight.div_(self.num_samples).view(b, c), -1) for weight in weights]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(batch_size={self.bs}, num_samples={self.num_samples}, std={self.std})"


class ISCAM(ScoreCAM):
    r"""Implements a class activation map extractor as described in `"IS-CAM: Integrated Score-CAM for axiomatic-based
    explanations" <https://arxiv.org/pdf/2010.03023.pdf>`_.

    The localization map is computed as follows:

    .. math::
        L^{(c)}_{ISS-CAM}(x, y) = ReLU\Big(\sum\limits_k w_k^{(c)} A_k(x, y)\Big)

    with the coefficient :math:`w_k^{(c)}` being defined as:

    .. math::
        w_k^{(c)} = softmax\Bigg(\frac{1}{N} \sum\limits_{i=1}^N
        \Big(Y^{(c)}(M_i) - Y^{(c)}(X_b)\Big)\Bigg)_k

    where :math:`N` is the number of samples used to smooth the weights,
    :math:`A_k(x, y)` is the activation of node :math:`k` in the target layer of the model at
    position :math:`(x, y)`, :math:`Y^{(c)}(X)` is the model output score for class :math:`c` before softmax
    for input :math:`X`, :math:`X_b` is a baseline image,
    and :math:`M_i` is defined as follows:

    .. math::
        M_i = \sum\limits_{j=0}^{i-1} \frac{j}{N}
        \frac{U(A_k) - \min\limits_m U(A_m)}{\max\limits_m  U(A_m) - \min\limits_m  U(A_m)} \odot X_b

    where :math:`\odot` refers to the element-wise multiplication, :math:`U` is the upsampling operation.

    >>> from torchvision.models import resnet18
    >>> from torchcam.methods import ISSCAM
    >>> model = resnet18(pretrained=True).eval()
    >>> cam = ISCAM(model, 'layer4')
    >>> with torch.no_grad(): out = model(input_tensor)
    >>> cam(class_idx=100)

    Args:
        model: input model
        target_layer: either the target layer itself or its name, or a list of those
        batch_size: batch size used to forward masked inputs
        num_samples: number of noisy samples used for weight computation
        input_shape: shape of the expected input tensor excluding the batch dimension
    """

    def __init__(
        self,
        model: nn.Module,
        target_layer: Optional[Union[Union[nn.Module, str], List[Union[nn.Module, str]]]] = None,
        batch_size: int = 32,
        num_samples: int = 10,
        input_shape: Tuple[int, ...] = (3, 224, 224),
        **kwargs: Any,
    ) -> None:

        super().__init__(model, target_layer, batch_size, input_shape, **kwargs)

        self.num_samples = num_samples

    @torch.no_grad()
    def _get_score_weights(self, activations: List[Tensor], class_idx: Union[int, List[int]]) -> List[Tensor]:

        b, c = activations[0].shape[:2]
        # (N * C, I, H, W)
        scored_inputs = [
            (act.unsqueeze(2) * self._input.unsqueeze(1)).view(b * c, *self._input.shape[1:]) for act in activations
        ]

        # Initialize weights
        weights = [torch.zeros(b * c, dtype=t.dtype).to(device=t.device) for t in activations]

        # (N, M)
        logits = self.model(self._input)
        idcs = torch.arange(b).repeat_interleave(c)

        for idx, scored_input in enumerate(scored_inputs):
            _coeff = 0.0
            # Process by chunk (GPU RAM limitation)
            for sidx in range(self.num_samples):
                _coeff += (sidx + 1) / self.num_samples

                # Process by chunk (GPU RAM limitation)
                for _idx in range(math.ceil(weights[idx].numel() / self.bs)):

                    _slice = slice(_idx * self.bs, min((_idx + 1) * self.bs, weights[idx].numel()))
                    # Get the softmax probabilities of the target class
                    cic = self.model(_coeff * scored_input[_slice]) - logits[idcs[_slice]]
                    if isinstance(class_idx, int):
                        weights[idx][_slice] += cic[:, class_idx]
                    else:
                        _target = torch.tensor(class_idx, device=cic.device)[idcs[_slice]]
                        weights[idx][_slice] += cic.gather(1, _target.view(-1, 1)).squeeze(1)

        # Reshape the weights (N, C)
        return [torch.softmax(weight.div_(self.num_samples).view(b, c), -1) for weight in weights]

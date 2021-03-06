from nose.plugins.skip import SkipTest
from nose.plugins.attrib import attr
import sys
import time
import unittest

import theano.sparse
if not theano.sparse.enable_sparse:
    raise SkipTest('Optional package sparse disabled')

import scipy.sparse
from scipy.signal import convolve2d
import scipy.sparse as sparse
import numpy

from theano import function, tensor
import theano
from theano.compat import next
from theano.sparse.sandbox import sp
from theano.sparse.tests.test_basic import random_lil
from theano.tests import unittest_tools as utt
from theano.sparse import verify_grad_sparse
from theano.sparse.tests.test_basic import sparse_random_inputs


class TestSP(unittest.TestCase):
    def test_convolution(self):
#        print '\n\n*************************************************'
#        print '           TEST CONVOLUTION'
#        print '*************************************************'

        # fixed parameters
        bsize = 10     # batch size
        imshp = (28, 28)
        kshp = (5, 5)
        nkern = 5
        ssizes = ((1, 1), (2, 2), (3, 3), (4, 4))
        convmodes = ('full', 'valid')

        # symbolic stuff
        bias = tensor.dvector()
        kerns = tensor.dmatrix()
        input = tensor.dmatrix()
        rng = numpy.random.RandomState(3423489)
        filters = rng.randn(nkern, numpy.prod(kshp))
        biasvals = rng.randn(nkern)

        for mode in ('FAST_COMPILE', 'FAST_RUN'):  # , profmode):
            ttot, ntot = 0, 0
            for conv_mode in convmodes:
                for ss in ssizes:

                    output, outshp = sp.convolve(kerns, kshp, nkern, input,\
                            imshp, ss, bias=bias, mode=conv_mode)
                    f = function([kerns, bias, input], output, mode=mode)

                    # now test with real values
                    img2d = numpy.arange(bsize * numpy.prod(imshp)).reshape(( \
                                                            bsize,) + imshp)
                    img1d = img2d.reshape(bsize, -1)

                    # create filters (need to be flipped to use convolve2d)
                    filtersflipped = numpy.zeros((nkern,) + kshp)
                    for k in range(nkern):
                        it = reversed(filters[k, :])
                        for i in range(kshp[0]):
                            for j in range(kshp[1]):
                                filtersflipped[k,i,j] = next(it)

                    # compute output with convolve2d
                    if conv_mode == 'valid':
                        fulloutshp = numpy.array(imshp) - numpy.array(kshp) + 1
                    else:
                        fulloutshp = numpy.array(imshp) + numpy.array(kshp) - 1
                    ntime1 = time.time()
                    refout = numpy.zeros((bsize,)+tuple(fulloutshp)+(nkern,))
                    for b in range(bsize):
                        for n in range(nkern):
                            refout[b,...,n] = convolve2d(img2d[b,:,:],
                                                         filtersflipped[n,...],
                                                         conv_mode)
                    ntot += time.time() - ntime1

                    # need to flatten images
                    bench1 = refout[:,0::ss[0],0::ss[1],:].reshape(bsize,-1,nkern)
                    bench1 += biasvals.reshape(1,1,nkern)

                    # swap the last two dimensions (output needs to be nkern x outshp)
                    bench1 = numpy.swapaxes(bench1,1,2)
                    ttime1 = time.time()
                    out1 = f(filters, biasvals, img1d)
                    ttot += time.time() - ttime1
                    temp = bench1.flatten() - out1.flatten()

                    assert (temp < 1e-5).all()

                    # test downward propagation -- symbolic stuff
                    #vis = tensor.grad(output, input, output)
                    #downprop = function([kerns,input], vis, mode=mode)
                    #visval = downprop(filters,img1d)
                    ## test downward propagation -- reference implementation
                    #pshape = (img1d.shape[0],numpy.prod(outshp[1:]),numpy.prod(kshp))
                    #patchstack = numpy.zeros(pshape)
                    #for bi in numpy.arange(pshape[0]): # batch index
                        #abspos = 0
                        #for outy in numpy.arange(outshp[1]):
                            #for outx in numpy.arange(outshp[2]):
                                #for ni in numpy.arange(nkern):
                                    #print 'filters[n,:].shape = ', filters[n,:].shape
                                    #print 'out1[bi,abspos].shape =',out1[bi,abspos].shape
                                    #patchstack[bi,abspos,:] = filters[n,:]*out1[bi,abspos]
                                    #abspos+=1
                    #patchstack = patchstack.reshape(1,-1)
                    #indices, indptr, spmat_shape, sptype, outshp = \
                            #sp.convolution_indices.conv_eval(imshp,kshp,ss,conv_mode)
                    #spmat = sparse.csc_matrix((numpy.ones_like(indices),indices,indptr),spmat_shape)
                    #visref = numpy.dot(patchstack, spmat.todense())

                    #print 'visval = ', visval
                    #print 'visref = ', visref

                    #assert numpy.all(visref==visval)


#            print '**** Convolution Profiling Results (',mode,') ****'
#            print 'Numpy processing time: ', ntot
#            print 'Theano processing time: ', ttot

        #profmode.print_summary()


    @attr('slow')
    def test_sparse(self):

#        print '\n\n*************************************************'
#        print '           TEST SPARSE'
#        print '*************************************************'

        # fixed parameters
        bsize = 10     # batch size
        imshp = (8, 8)
        kshp = (5,5)
        nkern = 1 # per output pixel
        ssizes = ((1,1),(2,2))
        convmodes = ('full','valid',)

        # symbolic stuff
        bias = tensor.dvector()
        kerns = tensor.dvector()
        input = tensor.dmatrix()
        rng = numpy.random.RandomState(3423489)

        import theano.gof as gof

        for mode in (None,):
            ntot, ttot = 0,0
            for conv_mode in convmodes:
                for ss in ssizes:

                    output, outshp = sp.applySparseFilter(kerns, kshp,\
                            nkern, input, imshp, ss, bias=bias, mode=conv_mode)
                    f = function([kerns, bias, input], output, mode=mode)

                    # build actual input images
                    img2d = numpy.arange(bsize*numpy.prod(imshp)).reshape((bsize,)+imshp)
                    img1d = img2d.reshape(bsize,-1)
                    zeropad_img = numpy.zeros((bsize,\
                                           img2d.shape[1]+2*(kshp[0]-1),\
                                           img2d.shape[2]+2*(kshp[1]-1)))
                    zeropad_img[:, kshp[0]-1:kshp[0]-1+img2d.shape[1],
                                   kshp[1]-1:kshp[1]-1+img2d.shape[2]] = img2d

                    # build kernel matrix -- flatten it for theano stuff
                    filters = numpy.arange(numpy.prod(outshp)*numpy.prod(kshp)).\
                                reshape(nkern,numpy.prod(outshp[1:]),numpy.prod(kshp))
                    spfilt = filters.flatten()
                    biasvals = numpy.arange(numpy.prod(outshp))

                    # compute output by hand
                    ntime1 = time.time()
                    refout = numpy.zeros((bsize,nkern,outshp[1],outshp[2]))
                    patch = numpy.zeros((kshp[0],kshp[1]))
                    for b in xrange(bsize):
                        for k in xrange(nkern):
                            pixi = 0 # pixel index in raster order
                            for j in xrange(outshp[1]):
                                for i in xrange(outshp[2]):
                                    n = j * ss[0]
                                    m = i * ss[1]
                                    patch = zeropad_img[b,n:n+kshp[0],m:m+kshp[1]]
                                    refout[b,k,j,i] = numpy.dot(filters[k,pixi,:],\
                                                            patch.flatten())
                                    pixi += 1
                    refout = refout.reshape(bsize,-1) + biasvals
                    ntot += time.time() - ntime1

                    # need to flatten images
                    ttime1 = time.time()
                    out1 = f(spfilt, biasvals, img1d)
                    ttot += time.time() - ttime1

                    temp = refout - out1
                    assert (temp < 1e-10).all()

                    # test downward propagation
                    vis = tensor.grad(0.5*tensor.sqr(output).sum(), input)
                    downprop = function([kerns,output], vis)
                    temp1 = time.time()
                    for zz in range(100):
                        visval = downprop(spfilt,out1)
                    indices, indptr, spmat_shape, sptype, outshp, kmap = \
                            sp.convolution_indices.sparse_eval(imshp,kshp,nkern,ss,conv_mode)
                    spmat = sparse.csc_matrix((spfilt[kmap],indices,indptr),spmat_shape)
                    visref = numpy.dot(out1,spmat.todense())
                    assert numpy.all(visref==visval), (visref, visval)

#            print '**** Sparse Profiling Results (',mode,') ****'
#            print 'Numpy processing time: ', ntot
#            print 'Theano processing time: ', ttot
        #profmode.print_summary()


    def test_multilayer_sparse(self):
        # fixed parameters
        bsize = 10     # batch size
        imshp = (5,5)
        kshp = ((3,3),(2,2))
        nkerns = (10,20) # per output pixel
        ssizes = ((1,1),(2,2))
        convmodes = ('full','valid',)

        # symbolic stuff
        kerns = [tensor.dvector(),tensor.dvector()]
        input = tensor.dmatrix()
        rng = numpy.random.RandomState(3423489)

        # build actual input images
        img2d = numpy.arange(bsize*numpy.prod(imshp)).reshape((bsize,)+imshp)
        img1d = img2d.reshape(bsize,-1)

        for mode in ('FAST_COMPILE','FAST_RUN'):
            for conv_mode in convmodes:
                for ss in ssizes:

                    l1hid, l1outshp = sp.applySparseFilter(kerns[0], kshp[0],\
                            nkerns[0], input, imshp, ss, mode=conv_mode)
                    l2hid, l2outshp = sp.applySparseFilter(kerns[1], kshp[1],\
                            nkerns[1], l1hid, l1outshp, ss, mode=conv_mode)

                    l1propup = function([kerns[0], input], l1hid, mode=mode)
                    l2propup = function([kerns[1], l1hid], l2hid, mode=mode)

                    # actual values
                    l1kernvals = numpy.arange(numpy.prod(l1outshp)*numpy.prod(kshp[0]))
                    l2kernvals = numpy.arange(numpy.prod(l2outshp)*numpy.prod(kshp[1])*nkerns[0])
                    l1hidval = l1propup(l1kernvals,img1d)
                    l2hidval = l2propup(l2kernvals,l1hidval)

    # this doesn't compare the output of anything... but I manually verified that the patches
    # are properly generated
    def test_multilayer_conv(self):
        # fixed parameters
        bsize = 10     # batch size
        imshp = (5,5)
        kshp = ((3,3),(2,2))
        nkerns = (3,6) # per output pixel
        ssizes = (((1,1),(2,2)),)
        convmodes = ('full',)#'valid',)

        # symbolic stuff
        kerns = [tensor.dmatrix(),tensor.dmatrix()]
        input = tensor.dmatrix()
        rng = numpy.random.RandomState(3423489)

        # build actual input images
        img2d = numpy.arange(bsize*numpy.prod(imshp)).reshape((bsize,)+imshp)
        img1d = img2d.reshape(bsize,-1)

        for mode in ('FAST_COMPILE','FAST_RUN'):
            for conv_mode in convmodes:
                for ss in ssizes:

                    l1hid, l1shp = sp.convolve(kerns[0], kshp[0],\
                            nkerns[0], input, imshp, ss[0], mode=conv_mode)
                    l1propup = function([kerns[0], input], l1hid, mode=mode)

                    #l1kernvals = numpy.random.rand(nkerns[0],numpy.prod(kshp[0]))
                    l1kernvals = numpy.arange(nkerns[0]*numpy.prod(kshp[0])).reshape(nkerns[0],numpy.prod(kshp[0]))
                    l1hidval = l1propup(l1kernvals,img1d)

                    # actual values
                    l2hid, l2shp = sp.convolve(kerns[1], kshp[1],\
                            nkerns[1], l1hid, l1shp, ss[1], mode=conv_mode)
                    l2propup = function([kerns[1], l1hid], l2hid, mode=mode)

                    #l2kernvals = numpy.random.rand(nkerns[1],numpy.prod(kshp[1])*nkerns[0])
                    l2kernvals = numpy.arange(nkerns[1]*numpy.prod(kshp[1])*nkerns[0]).reshape(nkerns[1],numpy.prod(kshp[1])*nkerns[0])
                    # for debugging, we bring things back to integers
                    l1hidval = numpy.arange(numpy.size(l1hidval)).reshape(l1hidval.shape)

                    l2hidval = l2propup(l2kernvals,l1hidval)


    def test_maxpool(self):
        # generate flatted images
        maxpoolshps = ((2,2),(3,3),(4,4),(5,5),(6,6))
        imval = numpy.random.rand(4,5,10,10)

        images = tensor.dmatrix()
        for maxpoolshp in maxpoolshps:

            # symbolic stuff
            output, outshp = sp.max_pool(images, imval.shape[1:], maxpoolshp)
            f = function([images,],[output,])
            output_val = f(imval.reshape(imval.shape[0],-1))

            # numeric verification
            my_output_val = numpy.zeros((imval.shape[0], imval.shape[1],
                                     imval.shape[2] // maxpoolshp[0],
                                     imval.shape[3] // maxpoolshp[1]))
            assert numpy.prod(my_output_val.shape[1:]) == numpy.prod(numpy.r_[imval.shape[1],outshp])

            for n in range(imval.shape[0]):
                for k in range(imval.shape[1]):
                    for i in range(imval.shape[2] // maxpoolshp[0]):
                        for j in range(imval.shape[3] // maxpoolshp[1]):
                            ii,jj = i*maxpoolshp[0], j*maxpoolshp[1]
                            patch = imval[n,k,ii:ii+maxpoolshp[0],jj:jj+maxpoolshp[1]]
                            my_output_val[n,k,i,j] = numpy.max(patch)
            my_output_val = my_output_val.reshape(imval.shape[0],-1)
            assert numpy.all(output_val == my_output_val)

            def mp(input):
                output, outshp = sp.max_pool(input, imval.shape[1:], maxpoolshp)
                return output
            utt.verify_grad(mp, [imval.reshape(imval.shape[0],-1)])


    def test_CSMGrad(self):
        imshp = (3,3)
        nkern = 1 # per output pixel
        kshp = (2,2)
        #ssizes = ((1,1),(2,2))
        ssizes = ((1,1),)
        #convmodes = ('full','valid',)
        convmodes = ('full',)

        kerns = tensor.dvector()
        indices = tensor.ivector()
        indptr = tensor.ivector()
        spmat_shape = tensor.ivector()

        for mode in ['FAST_COMPILE','FAST_RUN']:
            for conv_mode in convmodes:
                for ss in ssizes:
                    indvals, indptrvals, spshapevals, sptype, outshp, kmap = \
                            sp.convolution_indices.sparse_eval(imshp,kshp,nkern,ss,conv_mode)
                    kvals = numpy.random.random(nkern*numpy.prod(kshp)*numpy.prod(outshp)).flatten()

                    def d(kerns):
                        return theano.sparse.dense_from_sparse(
                                theano.sparse.CSM(sptype,kmap)(
                                    kerns, indvals, indptrvals, spshapevals))

                    # symbolic stuff
                    utt.verify_grad(d, [kvals])


if __name__ == '__main__':
    if 0:
        test_remove0()
        exit()
    if 1:
        testcase =  TestSP
        suite = unittest.TestLoader()
        suite = suite.loadTestsFromTestCase(testcase)
        unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        unittest.main()

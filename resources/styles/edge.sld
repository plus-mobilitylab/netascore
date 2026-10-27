<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.1.0" xmlns:ogc="http://www.opengis.net/ogc" xmlns:se="http://www.opengis.net/se" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.1.0/StyledLayerDescriptor.xsd">
 <NamedLayer>
  <se:Name>edge</se:Name>
  <UserStyle>
   <se:Name>edge</se:Name>
   <se:FeatureTypeStyle>
    <se:Rule>
     <se:Name>0 - 0,2</se:Name>
     <se:Description>
      <se:Title>0 - 0,2</se:Title>
     </se:Description>
     <ogc:Filter xmlns:ogc="http://www.opengis.net/ogc">
      <ogc:And>
       <ogc:PropertyIsGreaterThanOrEqualTo>
        <ogc:Function name="max"><ogc:PropertyName>index_bike_ft</ogc:PropertyName><ogc:PropertyName>index_bike_tf</ogc:PropertyName></ogc:Function>
        <ogc:Literal>0</ogc:Literal>
       </ogc:PropertyIsGreaterThanOrEqualTo>
       <ogc:PropertyIsLessThanOrEqualTo>
        <ogc:Function name="max"><ogc:PropertyName>index_bike_ft</ogc:PropertyName><ogc:PropertyName>index_bike_tf</ogc:PropertyName></ogc:Function>
        <ogc:Literal>0.20000000000000001</ogc:Literal>
       </ogc:PropertyIsLessThanOrEqualTo>
      </ogc:And>
     </ogc:Filter>
     <se:LineSymbolizer>
      <se:Stroke>
       <se:SvgParameter name="stroke">#d7191c</se:SvgParameter>
       <se:SvgParameter name="stroke-width">1</se:SvgParameter>
       <se:SvgParameter name="stroke-linejoin">bevel</se:SvgParameter>
       <se:SvgParameter name="stroke-linecap">square</se:SvgParameter>
      </se:Stroke>
     </se:LineSymbolizer>
    </se:Rule>
    <se:Rule>
     <se:Name>0,2 - 0,4</se:Name>
     <se:Description>
      <se:Title>0,2 - 0,4</se:Title>
     </se:Description>
     <ogc:Filter xmlns:ogc="http://www.opengis.net/ogc">
      <ogc:And>
       <ogc:PropertyIsGreaterThan>
        <ogc:Function name="max"><ogc:PropertyName>index_bike_ft</ogc:PropertyName><ogc:PropertyName>index_bike_tf</ogc:PropertyName></ogc:Function>
        <ogc:Literal>0.20000000000000001</ogc:Literal>
       </ogc:PropertyIsGreaterThan>
       <ogc:PropertyIsLessThanOrEqualTo>
        <ogc:Function name="max"><ogc:PropertyName>index_bike_ft</ogc:PropertyName><ogc:PropertyName>index_bike_tf</ogc:PropertyName></ogc:Function>
        <ogc:Literal>0.40000000000000002</ogc:Literal>
       </ogc:PropertyIsLessThanOrEqualTo>
      </ogc:And>
     </ogc:Filter>
     <se:LineSymbolizer>
      <se:Stroke>
       <se:SvgParameter name="stroke">#fdae61</se:SvgParameter>
       <se:SvgParameter name="stroke-width">1</se:SvgParameter>
       <se:SvgParameter name="stroke-linejoin">bevel</se:SvgParameter>
       <se:SvgParameter name="stroke-linecap">square</se:SvgParameter>
      </se:Stroke>
     </se:LineSymbolizer>
    </se:Rule>
    <se:Rule>
     <se:Name>0,4 - 0,6</se:Name>
     <se:Description>
      <se:Title>0,4 - 0,6</se:Title>
     </se:Description>
     <ogc:Filter xmlns:ogc="http://www.opengis.net/ogc">
      <ogc:And>
       <ogc:PropertyIsGreaterThan>
        <ogc:Function name="max"><ogc:PropertyName>index_bike_ft</ogc:PropertyName><ogc:PropertyName>index_bike_tf</ogc:PropertyName></ogc:Function>
        <ogc:Literal>0.40000000000000002</ogc:Literal>
       </ogc:PropertyIsGreaterThan>
       <ogc:PropertyIsLessThanOrEqualTo>
        <ogc:Function name="max"><ogc:PropertyName>index_bike_ft</ogc:PropertyName><ogc:PropertyName>index_bike_tf</ogc:PropertyName></ogc:Function>
        <ogc:Literal>0.59999999999999998</ogc:Literal>
       </ogc:PropertyIsLessThanOrEqualTo>
      </ogc:And>
     </ogc:Filter>
     <se:LineSymbolizer>
      <se:Stroke>
       <se:SvgParameter name="stroke">#ffffbf</se:SvgParameter>
       <se:SvgParameter name="stroke-width">1</se:SvgParameter>
       <se:SvgParameter name="stroke-linejoin">bevel</se:SvgParameter>
       <se:SvgParameter name="stroke-linecap">square</se:SvgParameter>
      </se:Stroke>
     </se:LineSymbolizer>
    </se:Rule>
    <se:Rule>
     <se:Name>0,6 - 0,8</se:Name>
     <se:Description>
      <se:Title>0,6 - 0,8</se:Title>
     </se:Description>
     <ogc:Filter xmlns:ogc="http://www.opengis.net/ogc">
      <ogc:And>
       <ogc:PropertyIsGreaterThan>
        <ogc:Function name="max"><ogc:PropertyName>index_bike_ft</ogc:PropertyName><ogc:PropertyName>index_bike_tf</ogc:PropertyName></ogc:Function>
        <ogc:Literal>0.59999999999999998</ogc:Literal>
       </ogc:PropertyIsGreaterThan>
       <ogc:PropertyIsLessThanOrEqualTo>
        <ogc:Function name="max"><ogc:PropertyName>index_bike_ft</ogc:PropertyName><ogc:PropertyName>index_bike_tf</ogc:PropertyName></ogc:Function>
        <ogc:Literal>0.80000000000000004</ogc:Literal>
       </ogc:PropertyIsLessThanOrEqualTo>
      </ogc:And>
     </ogc:Filter>
     <se:LineSymbolizer>
      <se:Stroke>
       <se:SvgParameter name="stroke">#abdda4</se:SvgParameter>
       <se:SvgParameter name="stroke-width">1</se:SvgParameter>
       <se:SvgParameter name="stroke-linejoin">bevel</se:SvgParameter>
       <se:SvgParameter name="stroke-linecap">square</se:SvgParameter>
      </se:Stroke>
     </se:LineSymbolizer>
    </se:Rule>
    <se:Rule>
     <se:Name>0,8 - 1</se:Name>
     <se:Description>
      <se:Title>0,8 - 1</se:Title>
     </se:Description>
     <ogc:Filter xmlns:ogc="http://www.opengis.net/ogc">
      <ogc:And>
       <ogc:PropertyIsGreaterThan>
        <ogc:Function name="max"><ogc:PropertyName>index_bike_ft</ogc:PropertyName><ogc:PropertyName>index_bike_tf</ogc:PropertyName></ogc:Function>
        <ogc:Literal>0.80000000000000004</ogc:Literal>
       </ogc:PropertyIsGreaterThan>
       <ogc:PropertyIsLessThanOrEqualTo>
        <ogc:Function name="max"><ogc:PropertyName>index_bike_ft</ogc:PropertyName><ogc:PropertyName>index_bike_tf</ogc:PropertyName></ogc:Function>
        <ogc:Literal>1</ogc:Literal>
       </ogc:PropertyIsLessThanOrEqualTo>
      </ogc:And>
     </ogc:Filter>
     <se:LineSymbolizer>
      <se:Stroke>
       <se:SvgParameter name="stroke">#2b83ba</se:SvgParameter>
       <se:SvgParameter name="stroke-width">1</se:SvgParameter>
       <se:SvgParameter name="stroke-linejoin">bevel</se:SvgParameter>
       <se:SvgParameter name="stroke-linecap">square</se:SvgParameter>
      </se:Stroke>
     </se:LineSymbolizer>
    </se:Rule>
   </se:FeatureTypeStyle>
  </UserStyle>
 </NamedLayer>
</StyledLayerDescriptor>
